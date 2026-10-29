from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class JobCreate(BaseModel):
    task: Literal["summarize", "extract"]
    text: str = Field(min_length=1, max_length=20000)

    @field_validator("text")
    @classmethod
    def non_blank(cls, value):
        if "\x00" in value:
            raise ValueError("Text cannot contain NUL characters")
        if not value.strip():
            raise ValueError("Text cannot be blank")
        return value


class JobView(BaseModel):
    id: str
    task: str
    status: Literal["queued", "running", "succeeded", "failed"]
    result: dict | None = None
    error: str | None = None
    attempts: int
    created_at: datetime
    finished_at: datetime | None = None


class Summary(BaseModel):
    summary: str = Field(min_length=1, max_length=10000)


class Extraction(BaseModel):
    emails: list[str] = Field(max_length=100)
    keywords: list[str] = Field(max_length=50)
