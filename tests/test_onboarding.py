"""Unit tests for onboarding rules that don't require a live database."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.enums import ClassRole
from app.services import class_service
from app.utils.codes import generate_code


def _user(class_id=None, class_role=None):
    # Lightweight stand-in: the guard only reads ``class_id``. (Beanie Documents
    # can't be instantiated before init_beanie, so we avoid the real model here.)
    return SimpleNamespace(class_id=class_id, class_role=class_role)


def test_generate_code_length_and_alphabet():
    code = generate_code(8)
    assert len(code) == 8
    assert set(code) <= set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
    # No ambiguous characters.
    assert not (set("O01IL") & set(code))


def test_user_without_class_passes_guard():
    # Should not raise for a user with no class.
    class_service._ensure_no_class(_user())


def test_user_with_class_is_blocked_from_make_or_join():
    user = _user(class_id="ABC12345", class_role=ClassRole.MEMBER)
    with pytest.raises(HTTPException) as exc:
        class_service._ensure_no_class(user)
    assert exc.value.status_code == 409
