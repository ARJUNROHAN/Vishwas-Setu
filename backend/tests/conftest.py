"""Shared fixtures: a fresh seeded database and a frozen clock so results never depend on the real date."""
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ["STORAGE_DIR"] = f"{_tmp}/storage"
os.environ["AUTO_SEED"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import clock, seed  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Institution, User  # noqa: E402

FIXED = datetime(2026, 11, 5, 5, 0)  # 10:30 IST, inside the demo public-notice window and ODL cycle
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


@pytest.fixture(scope="session")
def client():
    clock.set_frozen(FIXED)
    seed.run(seed=7)
    with TestClient(app) as c:
        yield c
    clock.set_frozen(None)


@pytest.fixture(autouse=True)
def _frozen():
    clock.set_frozen(FIXED)
    yield


def travel(days: float):
    clock.set_frozen(clock.now() + timedelta(days=days))


def login(c, username):
    r = c.post("/api/auth/login", json={"username": username, "password": seed.DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def tick(c):
    assert c.post("/api/tick", headers=login(c, "bureau")).status_code == 200


def inst_user(region_code="NRO", *, new=False, self_financing=None, name_like=None):
    with SessionLocal() as db:
        q = db.query(Institution).filter(Institution.region.has(code=region_code), Institution.is_new.is_(new))
        if name_like:
            q = db.query(Institution).filter(Institution.name.like(f"%{name_like}%"))
        insts = q.all()
        if self_financing is not None:
            insts = [i for i in insts if i.self_financing == self_financing]
        inst = insts[0]
        return db.query(User).filter(User.institution_id == inst.id).first().username, inst.id


def upload(c, h, name="evidence.pdf"):
    r = c.post("/api/files", headers=h, files={"file": (name, PDF, "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def submit(c, h, app_type, **extra):
    """Submit via the API with every mandatory checklist document uploaded."""
    types = {t["code"]: t for t in c.get("/api/application-types", headers=h).json()["types"]}
    docs = {item["doc_code"]: upload(c, h) for item in types[app_type].get("checklist", []) if item["mandatory"]}
    r = c.post("/api/applications", headers=h, json={"application_type": app_type, "documents": docs, **extra})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def act(c, h, app_id, action, remarks="ok", expect=200, **kw):
    r = c.post(f"/api/applications/{app_id}/actions", headers=h, json={"action": action, "remarks": remarks, **kw})
    assert r.status_code == expect, r.text
    return r.json()


def detail(c, h, app_id):
    r = c.get(f"/api/applications/{app_id}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def assignee_login(c, app):
    si = [s for s in app["stages"] if not s["completed_at"]][-1]
    with SessionLocal() as db:
        return login(c, db.get(User, si["assignee"]["id"]).username)
