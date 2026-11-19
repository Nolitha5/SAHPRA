"""
Shared pytest fixtures for Phase 1 (Tier 0 foundation) tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pytest
from sqlalchemy.engine import Engine

from shared.database import create_memory_engine, create_readonly_engine, create_write_engine
from shared.schema import init_database


@pytest.fixture()
def memory_engine() -> Engine:
    """A fresh, initialised in-memory database for a single test."""
    engine = create_memory_engine()
    init_database(engine)
    return engine


@pytest.fixture()
def file_db(tmp_path) -> tuple[str, Engine]:
    """A fresh, initialised file-backed database for a single test,
    returned together with its write engine. Used by tests that need
    a real file on disk (e.g. to subsequently open a read-only
    engine against it)."""
    db_path = str(tmp_path / "audit.db")
    engine = create_write_engine(db_path)
    init_database(engine)
    return db_path, engine


@pytest.fixture()
def seeded_file_db(file_db) -> tuple[str, Engine]:
    """A file-backed database pre-populated with one event, one
    finding and one decision, all in session "sess-seed"."""
    from sqlalchemy import insert

    from shared.schema import decisions, events, findings

    db_path, engine = file_db
    with engine.begin() as conn:
        conn.execute(
            insert(events).values(
                id="seed-e1",
                session_id="sess-seed",
                timestamp="2026-01-01T00:00:00.000Z",
                agent_name="s6_container_closure",
                action="run_s6",
                status="started",
            )
        )
        conn.execute(
            insert(findings).values(
                id="seed-f1",
                event_id="seed-e1",
                session_id="sess-seed",
                timestamp="2026-01-01T00:00:01.000Z",
                agent_name="s6_container_closure",
                section="S.6",
                verdict="COMPLIANT",
                severity="INFO",
                rationale="seed finding",
            )
        )
        conn.execute(
            insert(decisions).values(
                id="seed-d1",
                finding_id="seed-f1",
                session_id="sess-seed",
                timestamp="2026-01-01T00:00:02.000Z",
                gate_name="gate-1",
                assessor="assessor-1",
                decision="APPROVED",
                note="seed decision",
            )
        )
    return db_path, engine
