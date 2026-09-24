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
    """Older Generation rows (submitted before KIE_CREDITS_PER_VIDEO was set,
    or before cost tracking existed at all) have no kie_credits_cost. Every
    submission this app makes uses identical settings (10s, 9:16, 720p, no
    video input), so the currently configured rate is a correct — not just
    approximate — cost for those past rows too. Runs on every startup; a
    no-op once nothing is left to backfill, since the filter below only
    matches rows that still have a real submission but no cost recorded."""
    from app.config import KIE_CREDITS_PER_VIDEO, KIE_USD_PER_CREDIT
    from app.models import Generation

    if not KIE_CREDITS_PER_VIDEO:
        return

    credits = float(KIE_CREDITS_PER_VIDEO)
    usd = credits * float(KIE_USD_PER_CREDIT) if KIE_USD_PER_CREDIT else None

    db = SessionLocal()
    try:
        rows = (
            db.query(Generation)
            .filter(Generation.kie_task_id != "", Generation.kie_credits_cost.is_(None))
            .all()
        )
        for row in rows:
            row.kie_credits_cost = credits
            row.kie_usd_cost = usd
        if rows:
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
        },
    )

    _backfill_kie_costs()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
