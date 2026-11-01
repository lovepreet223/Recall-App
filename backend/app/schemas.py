from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


RatingName = Literal["again", "hard", "good", "easy"]


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ItemDraft(StrictModel):
    question: str = Field(min_length=5, max_length=1500)
    expected_points: list[str] = Field(min_length=1, max_length=8)

    @field_validator("expected_points")
    @classmethod
    def validate_points(cls, points: list[str]) -> list[str]:
        cleaned = [point.strip() for point in points]

        if any(not point or len(point) > 1500 for point in cleaned):
            raise ValueError(
                "Each expected point must contain 1–1500 characters."
            )

        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Expected points must not be duplicated.")

        return cleaned


class GenerateRequest(StrictModel):
    title: str = Field(min_length=2, max_length=160)
    notes: str = Field(min_length=20, max_length=20000)


class GeneratedItems(StrictModel):
    items: list[ItemDraft] = Field(min_length=1, max_length=5)


class OverlapCheck(StrictModel):
    proposal_index: int
    overlap: Literal["unique", "related", "near_duplicate"]
    closest_existing_index: int | None = None
    reason: str = Field(min_length=5, max_length=1000)
    recommendation: Literal["keep", "edit", "discard"]
    suggested_revision: str | None = None


class GeneratedItemsWithOverlap(StrictModel):
    items: list[ItemDraft] = Field(min_length=1, max_length=5)
    overlap_checks: list[OverlapCheck] = Field(
        min_length=1,
        max_length=5,
    )


class ReferenceDraftRequest(StrictModel):
    title: str = Field(min_length=2, max_length=160)
    rough_notes: str = Field(min_length=3, max_length=20000)
    use_web_search: bool = False


class WebSource(StrictModel):
    title: str | None = None
    url: str


class ReferenceDraft(StrictModel):
    reference_notes: str = Field(min_length=20, max_length=20000)
    sources: list[WebSource] = Field(default_factory=list, max_length=20)


class TopicCreate(GenerateRequest):
    items: list[ItemDraft] = Field(min_length=1, max_length=10)


class TopicUpdate(GenerateRequest):
    pass


class PauseRequest(StrictModel):
    paused: bool


class EvaluateRequest(StrictModel):
    request_id: UUID
    answer: str = Field(min_length=1, max_length=12000)
    assisted: bool = False


class ConfirmRequest(StrictModel):
    rating: RatingName


class PointCheck(StrictModel):
    point_index: int
    status: Literal["correct", "partial", "missing", "incorrect"]
    answer_evidence: str
    explanation: str


class Evaluation(StrictModel):
    checks: list[PointCheck]
    incorrect_claims: list[str]
    unverified_additions: list[str]
    short_feedback: str
    suggested_rating: RatingName


class AIResult(StrictModel):
    evaluation: Evaluation
    model: str
    input_tokens: int
    output_tokens: int