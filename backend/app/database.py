from sqlalchemy import event, text
from sqlmodel import Session, create_engine

from .config import DATA_DIR


DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DATA_DIR / "recall.db"

engine = create_engine(
    f"sqlite:///{DATABASE_PATH.as_posix()}",
    connect_args={
        "check_same_thread": False,
        "timeout": 15,
    },
)


@event.listens_for(engine, "connect")
def configure_sqlite(connection, _):
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def get_session():
    with Session(engine) as session:
        yield session


def initialize_database() -> None:
    """Create normal tables and the FTS index.

    Called during application startup. FTS5 is a SQLite virtual-table
    module; its index is separate from the normal SQLModel tables.
    """
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS review_item_fts USING fts5(
                question,
                expected_points,
                topic_title,
                item_id UNINDEXED
            )
        """))