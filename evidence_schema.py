"""Validated schema for document-level medical evidence records."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any
from urllib.parse import urlparse


ALLOWED_EVIDENCE_LEVELS = {
    "legacy_unverified",
    "reviewed_reference",
    "official_guidance",
    "clinical_guideline",
    "systematic_review",
}
ALLOWED_REVIEW_STATUSES = {"unreviewed", "source_verified", "clinically_reviewed"}


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    disease: str
    predicate: str
    claim: str
    source_name: str
    source_url: str
    publisher: str
    document_title: str
    published_at: str
    accessed_at: str
    evidence_level: str
    review_status: str
    section: str = ""
    locator: str = ""
    reviewer: str = ""
    reviewed_at: str = ""
    notes: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRecord":
        record = cls(**{field: str(data.get(field, "")).strip() for field in cls.__dataclass_fields__})
        record.validate()
        return record

    def validate(self) -> None:
        required = (
            "evidence_id", "disease", "predicate", "claim", "source_name",
            "source_url", "publisher", "document_title", "published_at",
            "accessed_at", "evidence_level", "review_status",
        )
        missing = [name for name in required if not getattr(self, name)]
        if missing:
            raise ValueError(f"missing evidence fields: {', '.join(missing)}")
        if self.evidence_level not in ALLOWED_EVIDENCE_LEVELS:
            raise ValueError(f"unsupported evidence_level: {self.evidence_level}")
        if self.review_status not in ALLOWED_REVIEW_STATUSES:
            raise ValueError(f"unsupported review_status: {self.review_status}")
        parsed = urlparse(self.source_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("source_url must be an absolute HTTPS URL")
        for field in ("published_at", "accessed_at"):
            try:
                date.fromisoformat(getattr(self, field))
            except ValueError as exc:
                raise ValueError(f"{field} must use YYYY-MM-DD") from exc
        if self.review_status == "clinically_reviewed" and not (self.reviewer and self.reviewed_at):
            raise ValueError("clinically_reviewed evidence requires reviewer and reviewed_at")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def retrieval_metadata(self) -> dict[str, str]:
        return {
            "source_name": self.source_name,
            "source_url": self.source_url,
            "updated_at": self.published_at,
            "evidence_level": self.evidence_level,
            "publisher": self.publisher,
            "document_title": self.document_title,
            "section": self.section,
            "locator": self.locator,
            "review_status": self.review_status,
        }
