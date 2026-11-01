import json
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, text, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import database as db
from . import llm
from .config import settings
from .models import ReviewAttempt, ReviewItem, Topic
from .schemas import (
    ConfirmRequest,
    EvaluateRequest,
    GenerateRequest,
    ItemDraft,
    PauseRequest,
    ReferenceDraftRequest,
    TopicCreate,
    TopicUpdate,
)
from .scheduling import create_card, schedule_review


SessionDep = Annotated[Session, Depends(db.get_session)]

ai_lock = threading.Lock()

MAX_OVERLAP_CANDIDATES = 8


@asynccontextmanager
async def lifespan(_app: FastAPI):
    SQLModel.metadata.create_all(db.engine)
    db.initialize_database()
    yield


app = FastAPI(
    title="Recall",
    lifespan=lifespan,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["localhost", "127.0.0.1", "testserver"],
)


@app.middleware("http")
async def require_local_client_header(request: Request, call_next):
    if (
        request.url.path.startswith("/api/")
        and request.method not in {"GET", "HEAD", "OPTIONS"}
        and request.headers.get("X-Recall-Client") != "web"
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": "Missing application client header."},
        )

    return await call_next(request)


@app.exception_handler(llm.AIError)
async def handle_ai_error(_request: Request, exc: llm.AIError):
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc)},
    )


def get_topic(session: Session, topic_id: str) -> Topic:
    topic = session.get(Topic, topic_id)

    if topic is None:
        raise HTTPException(404, "Topic not found.")

    return topic


def get_item(session: Session, item_id: str) -> ReviewItem:
    item = session.get(ReviewItem, item_id)

    if item is None:
        raise HTTPException(404, "Review item not found.")

    return item


def item_data(item: ReviewItem) -> dict:
    return {
        "id": item.id,
        "topic_id": item.topic_id,
        "question": item.question,
        "expected_points": json.loads(item.expected_points_json),
        "due_at": item.due_at,
        "paused": item.paused,
        "version": item.version,
        "created_at": item.created_at,
    }


def attempt_data(attempt: ReviewAttempt) -> dict:
    return {
        "id": attempt.id,
        "item_id": attempt.item_id,
        "question": attempt.question_snapshot,
        "reference": attempt.reference_snapshot,
        "expected_points": json.loads(
            attempt.expected_points_snapshot
        ),
        "answer": attempt.answer,
        "assisted": attempt.assisted,
        "feedback": json.loads(attempt.feedback_json),
        "suggested_rating": attempt.suggested_rating,
        "confirmed_rating": attempt.confirmed_rating,
        "attempted_at": attempt.attempted_at,
        "confirmed_at": attempt.confirmed_at,
        "scheduled_due_at": attempt.scheduled_due_at,
        "model": attempt.model,
        "input_tokens": attempt.input_tokens,
        "output_tokens": attempt.output_tokens,
    }


def active_pending(
    session: Session,
    item: ReviewItem,
) -> ReviewAttempt | None:
    return session.exec(
        select(ReviewAttempt)
        .where(
            ReviewAttempt.item_id == item.id,
            ReviewAttempt.item_version == item.version,
            ReviewAttempt.confirmed_at.is_(None),
        )
        .order_by(ReviewAttempt.attempted_at.desc())
    ).first()


def topic_data(session: Session, topic: Topic) -> dict:
    items = session.exec(
        select(ReviewItem)
        .where(ReviewItem.topic_id == topic.id)
        .order_by(ReviewItem.created_at)
    ).all()

    return {
        "id": topic.id,
        "title": topic.title,
        "notes": topic.notes,
        "created_at": topic.created_at,
        "items": [item_data(item) for item in items],
    }


def ensure_matching_request(
    attempt: ReviewAttempt,
    item_id: str,
    payload: EvaluateRequest,
):
    if (
        attempt.item_id != item_id
        or attempt.answer != payload.answer
        or attempt.assisted != payload.assisted
    ):
        raise HTTPException(
            409,
            "This request ID was already used for a different answer.",
        )


def index_review_item(
    connection,
    item: ReviewItem,
    topic: Topic,
) -> None:
    connection.execute(
        text("""
            INSERT INTO review_item_fts (
                question, expected_points, topic_title, item_id
            )
            VALUES (
                :question, :expected_points, :topic_title, :item_id
            )
        """),
        {
            "question": item.question,
            "expected_points": item.expected_points_json,
            "topic_title": topic.title,
            "item_id": item.id,
        },
    )


def remove_review_item_from_index(connection, item_id: str) -> None:
    connection.execute(
        text(
            "DELETE FROM review_item_fts WHERE item_id = :item_id"
        ),
        {"item_id": item_id},
    )


def find_overlap_candidates(
    session: Session,
    proposal: ItemDraft,
) -> list[dict]:
    query = llm.build_fts_query(
        f"{proposal.question} "
        f"{' '.join(proposal.expected_points)}"
    )

    if not query:
        return []

    result = session.execute(
        text("""
            SELECT
                review_item_fts.item_id,
                bm25(review_item_fts) AS relevance
            FROM review_item_fts
            WHERE review_item_fts MATCH :query
            ORDER BY relevance
            LIMIT :limit
        """),
        {
            "query": query,
            "limit": MAX_OVERLAP_CANDIDATES,
        },
    )

    rows = result.all()
    candidates: list[dict] = []

    for row in rows:
        item = session.get(ReviewItem, row.item_id)

        if item is None:
            continue

        topic = session.get(Topic, item.topic_id)

        if topic is None:
            continue

        candidates.append(
            {
                "topic_title": topic.title,
                "question": item.question,
                "expected_points": json.loads(
                    item.expected_points_json
                ),
            }
        )

    return candidates


@app.get("/api/status")
def status():
    return {
        "model": settings.openai_model,
        "api_key_configured": bool(settings.openai_api_key.strip()),
        "desired_retention": settings.desired_retention,
    }


@app.post("/api/generate-reference")
def generate_reference(payload: ReferenceDraftRequest):
    if not ai_lock.acquire(blocking=False):
        raise HTTPException(
            409,
            "Another AI request is running. Please wait.",
        )

    try:
        return llm.generate_reference_draft(
            payload.title,
            payload.rough_notes,
            payload.use_web_search,
        ).model_dump()
    finally:
        ai_lock.release()


@app.post("/api/generate")
def generate(payload: GenerateRequest, session: SessionDep):
    if not ai_lock.acquire(blocking=False):
        raise HTTPException(
            409,
            "Another AI request is running. Please wait.",
        )

    try:
        generated = llm.generate_items(
            payload.title,
            payload.notes,
        )

        proposals = [
            {
                "question": item.question,
                "expected_points": item.expected_points,
            }
            for item in generated.items
        ]

        candidate_lists = [
            find_overlap_candidates(session, item)
            for item in generated.items
        ]

        overlap_result = llm.check_overlap(
            proposals,
            [
                candidate
                for candidates in candidate_lists
                for candidate in candidates
            ],
        )

        return overlap_result.model_dump()

    finally:
        ai_lock.release()


@app.post("/api/topics", status_code=201)
def create_topic(payload: TopicCreate, session: SessionDep):
    topic = Topic(
        title=payload.title,
        notes=payload.notes,
    )
    session.add(topic)
    session.flush()

    for draft in payload.items:
        card_json, due_at = create_card()

        item = ReviewItem(
            topic_id=topic.id,
            question=draft.question,
            expected_points_json=json.dumps(
                draft.expected_points,
                ensure_ascii=False,
            ),
            card_json=card_json,
            due_at=due_at,
        )

        session.add(item)
        session.flush()
        index_review_item(session.connection(), item, topic)

    session.commit()
    session.refresh(topic)

    return topic_data(session, topic)


@app.get("/api/topics")
def list_topics(session: SessionDep):
    topics = session.exec(
        select(Topic).order_by(Topic.created_at.desc())
    ).all()

    return [topic_data(session, topic) for topic in topics]


@app.put("/api/topics/{topic_id}")
def edit_topic(
    topic_id: str,
    payload: TopicUpdate,
    session: SessionDep,
):
    topic = get_topic(session, topic_id)

    notes_changed = topic.notes != payload.notes

    topic.title = payload.title
    topic.notes = payload.notes
    session.add(topic)

    if notes_changed:
        items = session.exec(
            select(ReviewItem).where(
                ReviewItem.topic_id == topic_id
            )
        ).all()

        for item in items:
            card_json, due_at = create_card()

            item.card_json = card_json
            item.due_at = due_at
            item.version += 1

            session.add(item)

            connection = session.connection()
            remove_review_item_from_index(connection, item.id)
            index_review_item(connection, item, topic)

    session.commit()
    session.refresh(topic)

    return topic_data(session, topic)


@app.delete("/api/topics/{topic_id}")
def delete_topic(topic_id: str, session: SessionDep):
    get_topic(session, topic_id)

    items = session.exec(
        select(ReviewItem).where(
            ReviewItem.topic_id == topic_id
        )
    ).all()

    for item in items:
        remove_review_item_from_index(
            session.connection(),
            item.id,
        )

    item_ids = select(ReviewItem.id).where(
        ReviewItem.topic_id == topic_id
    )

    session.exec(
        delete(ReviewAttempt).where(
            ReviewAttempt.item_id.in_(item_ids)
        )
    )
    session.exec(
        delete(ReviewItem).where(
            ReviewItem.topic_id == topic_id
        )
    )
    session.exec(
        delete(Topic).where(Topic.id == topic_id)
    )

    session.commit()

    return {"ok": True}


@app.put("/api/items/{item_id}")
def edit_item(
    item_id: str,
    payload: ItemDraft,
    session: SessionDep,
):
    item = get_item(session, item_id)
    topic = get_topic(session, item.topic_id)

    card_json, due_at = create_card()

    item.question = payload.question
    item.expected_points_json = json.dumps(
        payload.expected_points,
        ensure_ascii=False,
    )
    item.card_json = card_json
    item.due_at = due_at
    item.version += 1

    session.add(item)

    connection = session.connection()
    remove_review_item_from_index(connection, item.id)
    index_review_item(connection, item, topic)

    session.commit()
    session.refresh(item)

    return item_data(item)


@app.patch("/api/items/{item_id}/pause")
def pause_item(
    item_id: str,
    payload: PauseRequest,
    session: SessionDep,
):
    item = get_item(session, item_id)

    if item.paused != payload.paused:
        item.paused = payload.paused
        item.version += 1
        session.add(item)
        session.commit()
        session.refresh(item)

    return item_data(item)


@app.delete("/api/items/{item_id}")
def delete_item(item_id: str, session: SessionDep):
    item = get_item(session, item_id)

    remove_review_item_from_index(session.connection(), item.id)

    session.exec(
        delete(ReviewAttempt).where(
            ReviewAttempt.item_id == item_id
        )
    )
    session.exec(
        delete(ReviewItem).where(ReviewItem.id == item_id)
    )

    session.commit()

    return {"ok": True}


@app.get("/api/queue")
def queue(session: SessionDep):
    now = time.time()

    rows = session.exec(
        select(ReviewItem, Topic)
        .join(Topic, ReviewItem.topic_id == Topic.id)
        .where(
            ReviewItem.paused.is_(False),
            ReviewItem.due_at <= now,
        )
        .order_by(ReviewItem.due_at)
    ).all()

    return [
        {
            "id": item.id,
            "topic_id": topic.id,
            "topic_title": topic.title,
            "question": item.question,
            "due_at": item.due_at,
            "pending_attempt": (
                attempt_data(pending)
                if (pending := active_pending(session, item))
                else None
            ),
        }
        for item, topic in rows
    ]


@app.get("/api/items/{item_id}/history")
def history(item_id: str, session: SessionDep):
    get_item(session, item_id)

    attempts = session.exec(
        select(ReviewAttempt)
        .where(ReviewAttempt.item_id == item_id)
        .order_by(ReviewAttempt.attempted_at.desc())
    ).all()

    return [attempt_data(attempt) for attempt in attempts]


@app.post("/api/items/{item_id}/evaluate")
def evaluate(
    item_id: str,
    payload: EvaluateRequest,
    session: SessionDep,
):
    request_id = str(payload.request_id)

    existing = session.exec(
        select(ReviewAttempt).where(
            ReviewAttempt.request_id == request_id
        )
    ).first()

    if existing:
        ensure_matching_request(existing, item_id, payload)
        return attempt_data(existing)

    item = get_item(session, item_id)

    if item.paused:
        raise HTTPException(409, "This item is paused.")

    if item.due_at > time.time():
        raise HTTPException(409, "This item is not due yet.")

    if pending := active_pending(session, item):
        return attempt_data(pending)

    topic = get_topic(session, item.topic_id)

    version = item.version
    question = item.question
    reference = topic.notes
    expected_points_json = item.expected_points_json
    attempted_at = time.time()

    session.rollback()

    if not ai_lock.acquire(blocking=False):
        raise HTTPException(
            409,
            "Another AI request is running. Please wait.",
        )

    try:
        result = llm.evaluate_answer(
            question=question,
            reference=reference,
            expected_points=json.loads(expected_points_json),
            answer=payload.answer,
            assisted=payload.assisted,
        )

        session.expire_all()
        item = get_item(session, item_id)

        if item.version != version or item.paused:
            raise HTTPException(
                409,
                "This item changed during evaluation. Reload Today.",
            )

        attempt = ReviewAttempt(
            request_id=request_id,
            item_id=item_id,
            item_version=version,
            question_snapshot=question,
            reference_snapshot=reference,
            expected_points_snapshot=expected_points_json,
            answer=payload.answer,
            assisted=payload.assisted,
            feedback_json=result.evaluation.model_dump_json(),
            suggested_rating=result.evaluation.suggested_rating,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            attempted_at=attempted_at,
        )

        session.add(attempt)

        try:
            session.commit()
        except IntegrityError:
            session.rollback()

            existing = session.exec(
                select(ReviewAttempt).where(
                    ReviewAttempt.request_id == request_id
                )
            ).first()

            if existing is None:
                raise

            ensure_matching_request(existing, item_id, payload)
            return attempt_data(existing)

        session.refresh(attempt)

        return attempt_data(attempt)

    finally:
        ai_lock.release()


@app.post("/api/attempts/{attempt_id}/confirm")
def confirm_review(
    attempt_id: str,
    payload: ConfirmRequest,
    session: SessionDep,
):
    attempt = session.get(ReviewAttempt, attempt_id)

    if attempt is None:
        raise HTTPException(404, "Review attempt not found.")

    if attempt.confirmed_at is not None:
        if attempt.confirmed_rating != payload.rating:
            raise HTTPException(
                409,
                "This attempt was already confirmed "
                "with a different rating.",
            )

        return attempt_data(attempt)

    item = get_item(session, attempt.item_id)

    if item.paused or item.version != attempt.item_version:
        raise HTTPException(
            409,
            "This review is stale because the item changed "
            "or was reviewed elsewhere. Reload Today.",
        )

    card_json, due_at, review_log_json = schedule_review(
        item.card_json,
        payload.rating,
        attempt.attempted_at,
    )

    result = session.exec(
        update(ReviewItem)
        .where(
            ReviewItem.id == item.id,
            ReviewItem.version == attempt.item_version,
            ReviewItem.paused.is_(False),
        )
        .values(
            card_json=card_json,
            due_at=due_at,
            version=attempt.item_version + 1,
        )
    )

    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(
            409,
            "Another change was saved first. Reload Today.",
        )

    attempt.confirmed_at = time.time()
    attempt.confirmed_rating = payload.rating
    attempt.scheduled_due_at = due_at
    attempt.review_log_json = review_log_json

    session.add(attempt)
    session.commit()
    session.refresh(attempt)

    return attempt_data(attempt)


@app.get("/api/export")
def export_data(session: SessionDep):
    topics = session.exec(select(Topic)).all()
    items = session.exec(select(ReviewItem)).all()
    attempts = session.exec(select(ReviewAttempt)).all()

    return {
        "format_version": 1,
        "exported_at": time.time(),
        "topics": [topic.model_dump() for topic in topics],
        "items": [item.model_dump() for item in items],
        "attempts": [
            attempt.model_dump() for attempt in attempts
        ],
    }


FRONTEND_DIST = (
    Path(__file__).resolve().parents[2] / "frontend" / "dist"
)

if FRONTEND_DIST.exists():
    app.mount(
        "/",
        StaticFiles(
            directory=FRONTEND_DIST,
            html=True,
        ),
        name="frontend",
    )