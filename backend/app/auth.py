"""Authentication (demo: username + password -> signed JWT) and role checks.

Production would federate officials through government SSO (OIDC via Keycloak) and add
TOTP for privileged roles; the interface below stays the same.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import User

SECRET = os.environ.get("JWT_SECRET") or secrets.token_hex(32)
ALGO = "HS256"
TOKEN_HOURS = 8
_bearer = HTTPBearer(auto_error=False)

ROLES = {
    "INSTITUTION": "Institution",
    "SCRUTINY_OFFICER": "Scrutiny officer",
    "RESCRUTINY_OFFICER": "Re-scrutiny officer",
    "EVC_COORDINATOR": "EVC coordinator",
    "EVC_MEMBER": "EVC member (expert)",
    "SHC_MEMBER": "Standing Hearing Committee member",
    "SAC_MEMBER": "Standing Appellate Committee member",
    "REGIONAL_HEAD": "Regional officer",
    "BUREAU": "Bureau officer (Regulation Bureau)",
    "COMPETENT_AUTHORITY": "Competent authority",
    "RULE_ADMIN": "Rule administrator",
    "ADMIN": "System administrator",
}
OFFICIAL_ROLES = set(ROLES) - {"INSTITUTION"}


def hash_password(pw: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 120_000)
    return f"pbkdf2${salt}${dk.hex()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        _, salt, _ = stored.split("$")
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(pw, salt), stored)


def issue_token(user: User) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": str(user.id), "role": user.role, "exp": exp}, SECRET, algorithm=ALGO)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
                 db: Session = Depends(get_db)) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        data = jwt.decode(creds.credentials, SECRET, algorithms=[ALGO])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, int(data["sub"]))
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    return user


def require(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot perform this action")
        return user
    return dep
