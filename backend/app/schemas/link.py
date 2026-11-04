from datetime import datetime
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator


class LinkCreate(BaseModel):
    original_url: str = Field(..., description="The destination URL (HTTP or HTTPS only)")
    custom_code: str | None = Field(
        None,
        min_length=3,
        max_length=16,
        description="Optional custom alias for the link",
    )
    title: str | None = Field(None, max_length=255, description="Optional title or label for the link")

    @field_validator("custom_code")
    @classmethod
    def validate_custom_code(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not re.match(r"^[a-zA-Z0-9_-]{3,16}$", v):
                raise ValueError("Custom code must be 3-16 characters and contain only letters, numbers, underscores, or hyphens.")
        return v


class LinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    short_code: str
    short_url: str
    original_url: str
    title: str | None = None
    click_count: int
    is_active: bool
    created_at: datetime


class LinkStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    short_code: str
    original_url: str
    title: str | None = None
    click_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
