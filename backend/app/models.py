import time
from uuid import uuid4

from sqlmodel import Field, SQLModel


def new_id() -> str:
    return str(uuid4())


class Topic(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    title: str
    notes: str
    created_at: float = Field(default_factory=time.time)


class ReviewItem(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    topic_id: str = Field(foreign_key="topic.id", index=True)

    question: str
    expected_points_json: str

    card_json: str
    due_at: float = Field(index=True)
    paused: bool = False

    version: int = 0
    created_at: float = Field(default_factory=time.time)


class ReviewAttempt(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    request_id: str = Field(index=True, unique=True)

    item_id: str = Field(foreign_key="reviewitem.id", index=True)
    item_version: int

    question_snapshot: str
    reference_snapshot: str
    expected_points_snapshot: str

    answer: str
    assisted: bool

    feedback_json: str
    suggested_rating: str

    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    attempted_at: float
    confirmed_at: float | None = None
    confirmed_rating: str | None = None

    scheduled_due_at: float | None = None
    review_log_json: str | None = None