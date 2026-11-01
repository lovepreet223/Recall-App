from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import create_engine

from app import database, llm
from app.main import app
from app.schemas import (
    AIResult,
    Evaluation,
    GeneratedItems,
    ItemDraft,
    PointCheck,
)


HEADERS = {"X-Recall-Client": "web"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_engine = create_engine(
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )

    monkeypatch.setattr(database, "engine", test_engine)

    with TestClient(app) as test_client:
        yield test_client

    test_engine.dispose()


@pytest.fixture
def fake_ai(monkeypatch):
    calls = {"count": 0}

    def fake_evaluate(**kwargs):
        calls["count"] += 1

        points = kwargs["expected_points"]
        answer = kwargs["answer"]

        evaluation = Evaluation(
            checks=[
                PointCheck(
                    point_index=index,
                    status="correct",
                    answer_evidence=answer,
                    explanation="Matches the reference.",
                )
                for index in range(len(points))
            ],
            incorrect_claims=[],
            unverified_additions=[],
            short_feedback="Correct independent recall.",
            suggested_rating="good",
        )

        return AIResult(
            evaluation=evaluation,
            model="mock-model",
            input_tokens=100,
            output_tokens=50,
        )

    monkeypatch.setattr(
        llm,
        "evaluate_answer",
        fake_evaluate,
    )

    return calls


def make_topic(client):
    response = client.post(
        "/api/topics",
        headers=HEADERS,
        json={
            "title": "Precision",
            "notes": (
                "Precision is the number of true positives divided "
                "by all predicted positives."
            ),
            "items": [
                {
                    "question": "Define precision.",
                    "expected_points": [
                        "Precision is TP divided by TP plus FP."
                    ],
                }
            ],
        },
    )

    assert response.status_code == 201

    return response.json()


def evaluate_item(client, item_id, request_id=None):
    return client.post(
        f"/api/items/{item_id}/evaluate",
        headers=HEADERS,
        json={
            "request_id": request_id or str(uuid4()),
            "answer": "Precision is TP / (TP + FP).",
            "assisted": False,
        },
    )


def test_manual_create_and_due_queue(client):
    topic = make_topic(client)

    response = client.get("/api/queue")
    assert response.status_code == 200

    queue = response.json()

    assert len(queue) == 1
    assert queue[0]["topic_id"] == topic["id"]
    assert "reference" not in queue[0]
    assert "expected_points" not in queue[0]


def test_evaluation_is_idempotent(client, fake_ai):
    topic = make_topic(client)
    item_id = topic["items"][0]["id"]
    request_id = str(uuid4())

    first = evaluate_item(client, item_id, request_id)
    second = evaluate_item(client, item_id, request_id)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert fake_ai["count"] == 1


def test_pending_review_survives_refresh(client, fake_ai):
    topic = make_topic(client)
    item_id = topic["items"][0]["id"]

    response = evaluate_item(client, item_id)
    attempt_id = response.json()["id"]

    queue = client.get("/api/queue").json()

    assert queue[0]["pending_attempt"]["id"] == attempt_id


def test_confirm_and_repeat_confirmation(client, fake_ai):
    topic = make_topic(client)
    item_id = topic["items"][0]["id"]

    attempt = evaluate_item(client, item_id).json()

    first = client.post(
        f"/api/attempts/{attempt['id']}/confirm",
        headers=HEADERS,
        json={"rating": "good"},
    )
    second = client.post(
        f"/api/attempts/{attempt['id']}/confirm",
        headers=HEADERS,
        json={"rating": "good"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["scheduled_due_at"] is not None
    assert client.get("/api/queue").json() == []


def test_edit_invalidates_pending_review(client, fake_ai):
    topic = make_topic(client)
    item_id = topic["items"][0]["id"]

    attempt = evaluate_item(client, item_id).json()

    edit = client.put(
        f"/api/items/{item_id}",
        headers=HEADERS,
        json={
            "question": "Explain precision using TP and FP.",
            "expected_points": [
                "Precision equals TP / (TP + FP)."
            ],
        },
    )
    assert edit.status_code == 200

    confirm = client.post(
        f"/api/attempts/{attempt['id']}/confirm",
        headers=HEADERS,
        json={"rating": "good"},
    )
    assert confirm.status_code == 409


def test_pause_removes_item_from_queue(client):
    topic = make_topic(client)
    item_id = topic["items"][0]["id"]

    response = client.patch(
        f"/api/items/{item_id}/pause",
        headers=HEADERS,
        json={"paused": True},
    )

    assert response.status_code == 200
    assert client.get("/api/queue").json() == []


def test_delete_topic_removes_its_items(client, fake_ai):
    topic = make_topic(client)
    item_id = topic["items"][0]["id"]

    evaluate_item(client, item_id)

    response = client.delete(
        f"/api/topics/{topic['id']}",
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert client.get("/api/topics").json() == []
    assert client.get("/api/queue").json() == []


def test_generation_can_be_mocked(client, monkeypatch):
    monkeypatch.setattr(
        llm,
        "generate_items",
        lambda title, notes: GeneratedItems(
            items=[
                ItemDraft(
                    question="Define precision.",
                    expected_points=["TP / (TP + FP)."],
                )
            ]
        ),
    )

    response = client.post(
        "/api/generate",
        headers=HEADERS,
        json={
            "title": "Precision",
            "notes": "Precision is TP divided by all predicted positives.",
        },
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_write_requires_client_header(client):
    response = client.post(
        "/api/generate",
        json={
            "title": "Precision",
            "notes": "Precision is TP divided by all predicted positives.",
        },
    )

    assert response.status_code == 403