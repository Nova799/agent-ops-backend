from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

try:
    from .config import DATABASE_URL
except ImportError:
    from config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    # Full-text search (FTS5) for traces
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE VIRTUAL TABLE IF NOT EXISTS trace_fts USING fts5(trace_id UNINDEXED, session_name, content)"
        )
        # indexes
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_traces_started_at ON traces(started_at)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_traces_session_name ON traces(session_name)")