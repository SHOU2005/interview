"""Authentication: OTP signup and login."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.db.models import User, UserRole
from app.schemas.auth import LoginRequest, SignupRequest, SignupVerifyRequest, TokenResponse
from app.services.auth_service import (
    create_otp,
    create_user_after_otp,
    email_allowed,
    verify_otp,
)

router = APIRouter()


@router.post("/signup/request")
def signup_request(body: SignupRequest, db: Session = Depends(get_db)):
    if not email_allowed(body.email):
        raise HTTPException(status_code=400, detail=f"Only {get_settings().ALLOWED_EMAIL_DOMAIN} emails allowed")
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    code, _ = create_otp(db, body.email, "signup")
    out = {"message": "OTP sent", "email": body.email}
    if get_settings().DEBUG:
        out["dev_otp"] = code
    return out


@router.post("/signup/verify", response_model=TokenResponse)
def signup_verify(body: SignupVerifyRequest, db: Session = Depends(get_db)):
    if not email_allowed(body.email):
        raise HTTPException(status_code=400, detail="Invalid email domain")
    if not verify_otp(db, body.email, body.otp, "signup"):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    try:
        user = create_user_after_otp(db, body.email, body.name, body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = create_access_token(
        str(user.id),
        {"role": user.role.value, "email": user.email},
    )
    return TokenResponse(
        access_token=token,
        role=user.role.value,
        name=user.name,
        email=user.email,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(
        str(user.id),
        {"role": user.role.value, "email": user.email},
    )
    return TokenResponse(
        access_token=token,
        role=user.role.value,
        name=user.name,
        email=user.email,
    )
