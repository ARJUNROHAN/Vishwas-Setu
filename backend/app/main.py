"""Application entry point: API, idempotency, request IDs, background deadline scheduler, built frontend."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import jwt
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from . import audit, clock, compliance, obligations as obl
from .api import router
from .auth import ALGO, SECRET
from .db import Base, SessionLocal, engine
from .models import IdempotencyRecord, User

log = logging.getLogger("vishwas-setu")
TICK_SECONDS = int(os.environ.get("TICK_SECONDS", "60"))
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST", Path(__file__).resolve().parents[2] / "frontend" / "dist"))


def _tick_once() -> dict:
    db = SessionLocal()
    try:
        stats = obl.tick(db)
        compliance.sync_statuses(db)
        db.commit()
        return stats
    finally:
        db.close()


async def _scheduler():
    """Deadline worker. State-based, so a restart or a missed run is recovered on the next tick."""
    while True:
        await asyncio.sleep(TICK_SECONDS)
        try:
            await asyncio.to_thread(_tick_once)
        except Exception:
            log.exception("scheduler tick failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        empty = (db.scalar(select(func.count(User.id))) or 0) == 0
    if empty and os.environ.get("AUTO_SEED", "1") == "1":
        from . import seed
        log.info("Seeding demo data: %s", seed.run())
    task = asyncio.create_task(_scheduler())
    yield
    task.cancel()


app = FastAPI(title="Vishwas Setu — AICTE Approval Workflow & Compliance Monitoring", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware,
                   allow_origins=[origin.strip() for origin in os.environ.get(
                       "CORS_ORIGINS", "http://localhost:5173,https://arjunrohan.github.io").split(",") if origin.strip()],
                   allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-Request-ID", "Idempotent-Replay"])


def _user_id_from(request: Request) -> int | None:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    try:
        return int(jwt.decode(auth[7:], SECRET, algorithms=[ALGO])["sub"])
    except Exception:
        return None


@app.middleware("http")
async def idempotency_and_request_id(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    token = audit.request_id_var.set(rid)
    try:
        key = request.headers.get("idempotency-key")
        uid = _user_id_from(request) if key and request.method in ("POST", "PUT", "PATCH") else None
        if key and uid:
            with SessionLocal() as db:
                prev = db.scalars(select(IdempotencyRecord).where(IdempotencyRecord.key == key,
                                                                  IdempotencyRecord.user_id == uid)).first()
                if prev:
                    if prev.method_path != f"{request.method} {request.url.path}":
                        return JSONResponse({"detail": "Idempotency-Key reused for a different request"}, status_code=422)
                    return Response(prev.response_body, status_code=prev.status_code, media_type="application/json",
                                    headers={"Idempotent-Replay": "true", "X-Request-ID": rid})
        resp = await call_next(request)
        if key and uid and resp.status_code < 500:
            body = b"".join([chunk async for chunk in resp.body_iterator])
            with SessionLocal() as db:
                db.add(IdempotencyRecord(key=key, user_id=uid, method_path=f"{request.method} {request.url.path}",
                                         status_code=resp.status_code, response_body=body.decode("utf-8", "replace"),
                                         created_at=clock.now()))
                try:
                    db.commit()
                except Exception:
                    db.rollback()
            resp = Response(body, status_code=resp.status_code, headers=dict(resp.headers), media_type=resp.media_type)
        resp.headers["X-Request-ID"] = rid
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        return resp
    finally:
        audit.request_id_var.reset(token)


app.include_router(router, prefix="/api")
app.include_router(router, prefix="/api/v1", include_in_schema=False)


@app.get("/api/health")
def health():
    return {"ok": True}


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        f = FRONTEND_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
