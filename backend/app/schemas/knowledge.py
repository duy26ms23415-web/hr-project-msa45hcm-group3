from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, StrictInt, field_validator, model_validator


class KnowledgeWrite(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50000)
    source_url: HttpUrl | None = None
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"] = "DRAFT"
    minimum_role: Literal["EMPLOYEE", "MANAGER", "HR", "ADMIN"] = "EMPLOYEE"

    @field_validator("title", "content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Không được để trống")
        return value.strip()


class KnowledgeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    document_id: int
    title: str
    content: str
    source_url: str | None
    status: str
    minimum_role: str
    updated_at: datetime
    document_code: str | None = None
    current_version_id: int | None = None


class KnowledgeTitleWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Không được để trống")
        return value.strip()


class KnowledgeSectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_code: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    heading: str = Field(min_length=1, max_length=300)
    page_start: StrictInt = Field(gt=0, le=100)
    page_end: StrictInt = Field(gt=0, le=100)
    is_answerable: StrictBool = True

    @field_validator("heading")
    @classmethod
    def heading_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Heading không được để trống")
        return value.strip()


class KnowledgeSectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    section_id: int
    version_id: int
    section_code: str
    heading: str
    page_start: int | None
    page_end: int | None
    anchor: str | None
    is_answerable: bool


class KnowledgeVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    version_id: int
    document_id: int
    version_number: int
    title: str
    minimum_role: str
    status: str
    sha256: str | None
    byte_size: int | None
    page_count: int | None
    mime_type: str | None
    effective_from: date | None
    effective_to: date | None
    created_at: datetime


class KnowledgeVersionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    minimum_role: Literal["EMPLOYEE", "MANAGER", "HR", "ADMIN"]
    effective_from: date | None = None
    effective_to: date | None = None
    sections: list[KnowledgeSectionInput] | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def valid_metadata(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("PDF_TITLE_INVALID")
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("PDF_EFFECTIVE_RANGE_INVALID")
        return self


class KnowledgeSectionsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sections: list[KnowledgeSectionInput] = Field(min_length=1, max_length=200)


class KnowledgeSourceRead(BaseModel):
    document_id: int
    version_id: int
    section_id: int
    title: str
    section_code: str
    heading: str
    page_start: int
    page_end: int
    anchor: str | None
