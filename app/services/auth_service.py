"""OTP signup and university domain validation."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import OtpCode, User, UserRole


def normalize_domain(domain: str) -> str:
    d = domain.strip().lower()
    if not d.startswith("@"):
        d = "@" + d
    return d


def email_allowed(email: str) -> bool:
    settings = get_settings()
    dom = normalize_domain(settings.ALLOWED_EMAIL_DOMAIN)
    return email.strip().lower().endswith(dom)


def hash_otp(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def create_otp(db: Session, email: str, purpose: str = "signup") -> tuple[str, OtpCode]:
    settings = get_settings()
    code = f"{secrets.randbelow(900000) + 100000:06d}"
    expires = datetime.now(timezone.utc) + timedelta(seconds=settings.OTP_EXPIRE_SECONDS)
    row = OtpCode(
        email=email.strip().lower(),
        code_hash=hash_otp(code),
        expires_at=expires,
        purpose=purpose,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return code, row


def verify_otp(db: Session, email: str, code: str, purpose: str = "signup") -> bool:
    email_l = email.strip().lower()
    row = (
        db.query(OtpCode)
        .filter(OtpCode.email == email_l, OtpCode.purpose == purpose)
        .order_by(OtpCode.id.desc())
        .first()
    )
    if not row:
        return False
    if row.expires_at < datetime.now(timezone.utc):
        return False
    return row.code_hash == hash_otp(code.strip())


def create_user_after_otp(db: Session, email: str, name: str, password: str) -> User:
    if db.query(User).filter(User.email == email.strip().lower()).first():
        raise ValueError("Email already registered")
    u = User(
        email=email.strip().lower(),
        name=name,
        password_hash=hash_password(password),
        role=UserRole.student,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u
