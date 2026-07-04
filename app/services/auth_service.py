"""Authentication business logic: registration, email verification, login, reset.

Routes call into this module; this module talks to the models and the email
service. New accounts must verify their email (OTP) before they can log in.
"""

import secrets
from datetime import datetime, timedelta, timezone

from beanie import PydanticObjectId
from fastapi import HTTPException, status

from app.core import rate_limit
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResendOtpRequest,
    ResetPasswordRequest,
    SignupResponse,
    TokenResponse,
    VerifyEmailRequest,
)
from app.schemas.user import UserPublic
from app.services import email_service
from app.utils.codes import generate_otp

# Shown when the inline send failed (after retries). OTP codes are short-lived
# secrets, so we don't persist them for background retry — we ask the user to
# request a fresh one rather than falsely claiming "sent".
_OTP_SEND_FAILED_MSG = "We couldn't send your verification code just now. Please tap Resend to try again."


def to_public(user: User) -> UserPublic:
    """Map a User document to its public DTO."""
    return UserPublic(
        id=str(user.id),
        email=user.email,
        name=user.name,
        is_active=user.is_active,
        class_id=user.class_id,
        class_role=user.class_role,
        digest_enabled=user.digest_enabled,
        created_at=user.created_at,
    )


def _set_otp(user: User, purpose: str) -> str:
    code = generate_otp()
    user.otp_code = code
    user.otp_purpose = purpose
    user.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes)
    return code


def _otp_valid(user: User, otp: str, purpose: str) -> bool:
    if not user.otp_code or user.otp_purpose != purpose:
        return False
    expires = user.otp_expires_at
    if expires is not None:
        # Mongo round-trips datetimes as naive UTC; normalize before comparing.
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            return False
    return secrets.compare_digest(user.otp_code, otp)


def _clear_otp(user: User) -> None:
    user.otp_code = None
    user.otp_purpose = None
    user.otp_expires_at = None


async def register_user(payload: RegisterRequest) -> SignupResponse:
    """Create an unverified account and email a verification code."""
    rate_limit.hit(f"register:{payload.email}", limit=10, window_seconds=3600)
    existing = await User.find_one(User.email == payload.email)
    if existing is not None:
        if existing.is_verified:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            )
        # Unverified re-registration: refresh details and resend the code.
        existing.name = payload.name
        existing.hashed_password = hash_password(payload.password)
        code = _set_otp(existing, "signup")
        await existing.save()
        sent = await email_service.send_otp_email(existing.email, existing.name, code, "signup")
        return SignupResponse(
            email=existing.email,
            message="We sent a new code to your email." if sent else _OTP_SEND_FAILED_MSG,
        )

    user = User(
        email=payload.email,
        name=payload.name,
        hashed_password=hash_password(payload.password),
        is_verified=False,
    )
    code = _set_otp(user, "signup")
    await user.insert()
    sent = await email_service.send_otp_email(user.email, user.name, code, "signup")
    return SignupResponse(
        email=user.email,
        message=(
            "We sent a 6-digit verification code to your email." if sent else _OTP_SEND_FAILED_MSG
        ),
    )


async def verify_email(payload: VerifyEmailRequest) -> TokenResponse:
    """Confirm the signup OTP, mark the user verified, and log them in."""
    rate_limit.hit(f"verify:{payload.email}", limit=10, window_seconds=600)
    user = await User.find_one(User.email == payload.email)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code.")
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email is already verified. Please log in.",
        )
    if not _otp_valid(user, payload.otp, "signup"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code.")

    user.is_verified = True
    _clear_otp(user)
    await user.save()
    rate_limit.reset(f"verify:{payload.email}")
    return _build_token_response(user)


async def resend_otp(payload: ResendOtpRequest) -> None:
    rate_limit.hit(f"resend:{payload.email}", limit=5, window_seconds=600)
    user = await User.find_one(User.email == payload.email)
    if user is not None and not user.is_verified:
        code = _set_otp(user, "signup")
        await user.save()
        await email_service.send_otp_email(user.email, user.name, code, "signup")


async def authenticate_user(payload: LoginRequest) -> TokenResponse:
    """Verify credentials and return an access token, or raise."""
    user = await User.find_one(User.email == payload.email)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password."
        )
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email before logging in.",
        )
    return _build_token_response(user)


async def forgot_password(payload: ForgotPasswordRequest) -> None:
    """Email a reset code. Always succeeds silently (don't reveal if email exists)."""
    rate_limit.hit(f"forgot:{payload.email}", limit=5, window_seconds=900)
    user = await User.find_one(User.email == payload.email)
    if user is not None:
        code = _set_otp(user, "reset")
        await user.save()
        await email_service.send_otp_email(user.email, user.name, code, "reset")


async def reset_password(payload: ResetPasswordRequest) -> None:
    rate_limit.hit(f"reset:{payload.email}", limit=10, window_seconds=900)
    user = await User.find_one(User.email == payload.email)
    if user is None or not _otp_valid(user, payload.otp, "reset"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired code.")
    user.hashed_password = hash_password(payload.new_password)
    user.is_verified = True  # proving email ownership also verifies the account
    _clear_otp(user)
    await user.save()
    rate_limit.reset(f"reset:{payload.email}")


async def update_preferences(user: User, digest_enabled: bool | None) -> UserPublic:
    """Update the current user's notification preference."""
    if digest_enabled is not None:
        user.digest_enabled = digest_enabled
        await user.save()
    return to_public(user)


async def get_user_by_id(user_id: str) -> User | None:
    """Fetch a user by its string id, returning None for missing/invalid ids."""
    try:
        object_id = PydanticObjectId(user_id)
    except (ValueError, TypeError):
        return None
    return await User.get(object_id)


def _build_token_response(user: User) -> TokenResponse:
    token = create_access_token(subject=str(user.id))
    return TokenResponse(access_token=token, user=to_public(user))
