
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.connection import get_db
from app.database.models import User, RefreshSession
from app.security.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.security.rate_limit import limiter
from app.services.email_service import send_verification_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
bearer_scheme = HTTPBearer()

VERIFICATION_CODE_HOURS = 24


REFRESH_TOKEN_DAYS = 30
REFRESH_COOKIE_NAME = "adri_refresh"


def create_refresh_session(user_id: int, db: Session) -> str:
    token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    session = RefreshSession(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_DAYS),
    )
    db.add(session)
    db.commit()

    return token


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=REFRESH_TOKEN_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/api/auth",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/auth",
        secure=True,
        httponly=True,
        samesite="lax",
    )


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")


def hash_verification_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def create_verification_code():
    code = f"{secrets.randbelow(1_000_000):06d}"
    code_hash = hash_verification_code(code)
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=VERIFICATION_CODE_HOURS
    )
    return code, code_hash, expires_at


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
    code, code_hash, expires_at = create_verification_code()

    user.verification_token_hash = code_hash
    user.verification_expires_at = expires_at
    db.commit()

    try:
        send_verification_email(user.email, code)
        return True
    except Exception:
        logger.exception("Verification code email failed")
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

    user = User(
        email=data.email,
        username=data.username,
        hashed_password=hash_password(data.password),
        is_verified=False,
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

    sent = issue_verification_email(user, db)

    if not sent:
        logger.error("Could not send verification code to %s", user.email)

    return {
        "message": (
            "Account created. Please enter the six-digit "
            "verification code sent to your email."
            if sent else
            "Account created, but the verification code could not be sent. "
            "Please request a new code."
        ),
        "email_verification_required": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
        },
    }




@router.post("/verify-email")
@limiter.limit("5/minute")
def verify_email(
    request: Request,
    data: VerifyEmailRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or user.is_verified:
        raise HTTPException(
            status_code=400,
            detail="Invalid verification request.",
        )

    if not user.verification_token_hash or not user.verification_expires_at:
        raise HTTPException(
            status_code=400,
            detail="No active verification code. Request a new code.",
        )

    expires_at = user.verification_expires_at

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail="Verification code expired. Request a new code.",
        )

    submitted_hash = hash_verification_code(data.code)

    if not secrets.compare_digest(
        submitted_hash,
        user.verification_token_hash,
    ):
        raise HTTPException(
            status_code=400,
            detail="Incorrect verification code.",
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
@limiter.limit("3/minute")
def resend_verification(
    request: Request,
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
def login(
    data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    if not user.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email before logging in.",
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_session(user.id, db)
    set_refresh_cookie(response, refresh_token)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
        },
    }



@router.post("/refresh")
def refresh_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)

    def unauthorized(clear_cookie=True):
        if clear_cookie:
            clear_refresh_cookie(response)
        raise HTTPException(
            status_code=401,
            detail="Session expired. Please log in again.",
        )

    if not raw_token:
        unauthorized()

    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    try:
        # Lock the session row to prevent concurrent token rotation.
        session = (
            db.query(RefreshSession)
            .filter(RefreshSession.token_hash == token_hash)
            .with_for_update()
            .first()
        )

        if not session:
            unauthorized()

        if session.revoked_at is not None:
            # Another request may already have rotated this token.
            # Preserve the replacement cookie set by that request.
            unauthorized(clear_cookie=False)

        now = datetime.now(timezone.utc)
        expires_at = session.expires_at

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        user = db.query(User).filter(User.id == session.user_id).first()

        if (
            expires_at <= now
            or not user
            or not user.is_active
            or not user.is_verified
        ):
            session.revoked_at = now
            db.commit()
            unauthorized()

        # Revoke the old token and create its replacement in one transaction.
        new_refresh_token = secrets.token_urlsafe(48)
        new_token_hash = hashlib.sha256(
            new_refresh_token.encode("utf-8")
        ).hexdigest()

        session.revoked_at = now

        db.add(
            RefreshSession(
                user_id=user.id,
                token_hash=new_token_hash,
                expires_at=now + timedelta(days=REFRESH_TOKEN_DAYS),
            )
        )

        db.commit()
        set_refresh_cookie(response, new_refresh_token)

        return {
            "access_token": create_access_token(user.id),
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
            },
        }

    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise



@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)

    if raw_token:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        session = db.query(RefreshSession).filter(
            RefreshSession.token_hash == token_hash
        ).first()

        if session and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc)
            db.commit()

    clear_refresh_cookie(response)
    return {"message": "Logged out successfully"}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "username": current_user.username,
        "is_active": current_user.is_active,
        "is_verified": current_user.is_verified,
    }
