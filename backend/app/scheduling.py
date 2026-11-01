from datetime import datetime, timezone

from fsrs import Card, Rating, Scheduler

from .config import settings


RATINGS = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
}


def get_scheduler() -> Scheduler:
    return Scheduler(
        desired_retention=settings.desired_retention,
        enable_fuzzing=False,
    )


def create_card() -> tuple[str, float]:
    card = Card()
    return card.to_json(), card.due.timestamp()


def schedule_review(
    card_json: str,
    rating: str,
    attempted_at: float,
) -> tuple[str, float, str]:
    card = Card.from_json(card_json)

    review_time = datetime.fromtimestamp(
        attempted_at,
        tz=timezone.utc,
    )

    updated_card, review_log = get_scheduler().review_card(
        card,
        RATINGS[rating],
        review_datetime=review_time,
    )

    return (
        updated_card.to_json(),
        updated_card.due.timestamp(),
        review_log.to_json(),
    )