"""Shared utilities for the Study Partner backend."""

import uuid


def safe_uuid(value: str | None) -> uuid.UUID | None:
    """Parse a UUID string safely, returning None on invalid input."""
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def require_uuid(value: str | None, field_name: str = "id") -> uuid.UUID:
    """Parse a UUID string, raising 400 if invalid."""
    from fastapi import HTTPException, status

    result = safe_uuid(value)
    if result is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} format",
        )
    return result
