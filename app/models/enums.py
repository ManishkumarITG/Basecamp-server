"""Domain role enumerations shared by models and schemas."""

from enum import Enum


class ClassRole(str, Enum):
    """A user's role at the Class level."""

    SUPER_ADMIN = "super_admin"  # creator / owner of the class
    MEMBER = "member"  # joined the class


class TeamRole(str, Enum):
    """A user's role within a Team."""

    ADMIN = "admin"
    MEMBER = "member"
