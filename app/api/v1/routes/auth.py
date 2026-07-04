"""Authentication routes. Handlers stay thin and delegate to ``auth_service``."""

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResendOtpRequest,
    ResetPasswordRequest,
    SignupResponse,
    TokenResponse,
    UpdateMeRequest,
    VerifyEmailRequest,
)
from app.schemas.user import UserPublic
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest) -> SignupResponse:
    """Create an account (unverified) and email a verification code."""
    return await auth_service.register_user(payload)


@router.post("/verify-email", response_model=TokenResponse)
async def verify_email(payload: VerifyEmailRequest) -> TokenResponse:
    """Confirm the signup code and return a JWT (logs the user in)."""
    return await auth_service.verify_email(payload)


@router.post("/resend-otp", response_model=MessageResponse)
async def resend_otp(payload: ResendOtpRequest) -> MessageResponse:
    await auth_service.resend_otp(payload)
    return MessageResponse(message="If that account needs verification, a new code is on its way.")


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> TokenResponse:
    """Authenticate a user and return a JWT."""
    return await auth_service.authenticate_user(payload)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(payload: ForgotPasswordRequest) -> MessageResponse:
    await auth_service.forgot_password(payload)
    return MessageResponse(message="If that email exists, we've sent a reset code.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(payload: ResetPasswordRequest) -> MessageResponse:
    await auth_service.reset_password(payload)
    return MessageResponse(message="Your password has been reset. You can now log in.")


@router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    """Return the currently authenticated user (demonstrates the auth dependency)."""
    return auth_service.to_public(current_user)


@router.patch("/me", response_model=UserPublic)
async def update_me(
    payload: UpdateMeRequest, current_user: User = Depends(get_current_user)
) -> UserPublic:
    """Update the current user's preferences (e.g. digest on/off)."""
    return await auth_service.update_preferences(current_user, payload.digest_enabled)
