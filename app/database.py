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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
