from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "ai_ugc.db"

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _ensure_columns(table: str, columns: dict[str, str]) -> None:
    """Adds any of `columns` ({name: SQL type}) missing from an existing SQLite
    table. create_all() only creates whole new tables — it never adds columns
    to one that already exists — and this app has no migration framework, so
    this is what keeps an existing local database (real character/product/
    generation history) working after a model gains a new column."""
    with engine.connect() as conn:
        existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
        for name, coltype in columns.items():
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {coltype}")
        conn.commit()


def _backfill_kie_costs() -> None:
    """Older Generation rows (submitted before cost tracking existed, or
    before duration/resolution became per-video choices) have no
    kie_credits_cost. The migration below defaults duration/resolution to
    "10"/"720p" for any row that predates those columns — which is correct,
    not a guess, since that was the only combination the app could ever
    submit before this feature — so looking those values up in CREDIT_TABLE
    gives the real cost for those past rows too. Runs on every startup; a
    no-op once nothing is left to backfill, since the filter below only
    matches rows that still have a real submission but no cost recorded."""
    from app.config import KIE_USD_PER_CREDIT
    from app.integrations.kie import credits_for
    from app.models import Generation

    db = SessionLocal()
    try:
        rows = (
            db.query(Generation)
            .filter(Generation.kie_task_id != "", Generation.kie_credits_cost.is_(None))
            .all()
        )
        changed = False
        for row in rows:
            credits = credits_for(row.duration, row.resolution)
            if credits is None:
                continue
            row.kie_credits_cost = credits
            row.kie_usd_cost = credits * float(KIE_USD_PER_CREDIT) if KIE_USD_PER_CREDIT else None
            changed = True
        if changed:
            db.commit()
    finally:
        db.close()


def init_db():
    from app import models  # noqa: F401 — registers models on Base before create_all

    Base.metadata.create_all(bind=engine)

    _ensure_columns(
        "generations",
        {
            "vision_input_tokens": "INTEGER DEFAULT 0",
            "vision_output_tokens": "INTEGER DEFAULT 0",
            "vision_cost_usd": "FLOAT",
            "kie_credits_cost": "FLOAT",
            "kie_usd_cost": "FLOAT",
            # Defaults match what every row predating these columns actually
            # used (the only combination the app could submit before now) —
            # not placeholders, the real historical values.
            "duration": "VARCHAR DEFAULT '10'",
            "aspect_ratio": "VARCHAR DEFAULT '9:16'",
            "resolution": "VARCHAR DEFAULT '720p'",
        },
    )

    _backfill_kie_costs()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
