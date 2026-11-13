
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database.connection import get_db
from app.database.models import User
from app.security.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.services.email_service import send_verification_email

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
bearer_scheme = HTTPBearer()

VERIFICATION_TOKEN_HOURS = 24


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


def hash_verification_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_verification_token():
    token = secrets.token_urlsafe(32)
    token_hash = hash_verification_token(token)
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=VERIFICATION_TOKEN_HOURS
    )
    return token, token_hash, expires_at


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except Exception:
        raise unauthorized

    user = db.query(User).filter(User.id == user_id).first()

    if not user or not user.is_active:
        raise unauthorized

    return user


def issue_verification_email(user: User, db: Session) -> bool:
    token, token_hash, expires_at = create_verification_token()

    user.verification_token_hash = token_hash
    user.verification_expires_at = expires_at

    db.commit()

    try:
        send_verification_email(user.email, token)
        return True
    except Exception:
        return False


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(
        (User.email == data.email) |
        (User.username == data.username)
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email or username already registered",
        )

    token, token_hash, expires_at = create_verification_token()

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        is_verified=False,
        verification_token_hash=token_hash,
        verification_expires_at=expires_at,
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email or username already registered",
        )

    try:
        send_verification_email(user.email, token)
        message = (
            "Account created successfully. "
            "Please check your email to verify your account."
        )
    except Exception:
        message = (
            "Account created, but the verification email could not be sent. "
            "Please use the resend verification option."
        )

    return {
        "message": message,
        "email_verification_required": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
        },
    }


@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    if not token:
        raise HTTPException(
            status_code=400,
            detail="Verification token is required",
        )

    token_hash = hash_verification_token(token)

    user = db.query(User).filter(
        User.verification_token_hash == token_hash
    ).first()

    if not user:
        raise HTTPException(
            status_code=400,
            detail="Invalid or already used verification link",
        )

    if not user.verification_expires_at:
        raise HTTPException(
            status_code=400,
            detail="Verification link has expired",
        )

    expires_at = user.verification_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail="Verification link has expired. Request a new one.",
        )

    user.is_verified = True
    user.verification_token_hash = None
    user.verification_expires_at = None

    db.commit()

    return {
        "message": "Email verified successfully. You can now log in.",
        "verified": True,
    }


@router.post("/resend-verification")
def resend_verification(
    data: ResendVerificationRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == data.email).first()

    generic_message = (
        "If an unverified account exists for this email, "
        "a verification email will be sent."
    )

    if not user or user.is_verified or not user.is_active:
        return {"message": generic_message}

    sent = issue_verification_email(user, db)

    if not sent:
        raise HTTPException(
            status_code=503,
            detail="Unable to send verification email. Please try again later.",
        )

    return {"message": generic_message}


@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    if not user.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email before logging in.",
        )

    token = create_access_token(user.id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
        },
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "is_active": current_user.is_active,
        "is_verified": current_user.is_verified,
    }
