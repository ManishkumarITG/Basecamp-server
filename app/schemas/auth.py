"""Auth request/response DTOs."""

from pydantic import BaseModel, EmailStr, Field

from app.schemas.user import UserPublic


class RegisterRequest(BaseModel):
    """Payload for ``POST /auth/register``."""

    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    """Payload for ``POST /auth/login``."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """JWT plus the authenticated user, returned by login and email verification."""

    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class SignupResponse(BaseModel):
    """Returned by register: account created, email verification pending."""

    email: EmailStr
    message: str


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=4, max_length=10)


class ResendOtpRequest(BaseModel):
    email: EmailStr


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=4, max_length=10)
    new_password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    message: str


class UpdateMeRequest(BaseModel):
    """Update the current user's preferences."""

    digest_enabled: bool | None = None
