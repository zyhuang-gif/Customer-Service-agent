import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

import app.main as main_module
import app.schema_migrations as schema_migrations
from app.schema_migrations import ensure_conversation_last_message_at


def _create_legacy_schema(engine):
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE conversations (
                    id VARCHAR PRIMARY KEY,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id VARCHAR NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
        )


def test_adds_last_message_at_and_backfills_from_latest_message_or_created_at():
    engine = create_engine("sqlite://")
    _create_legacy_schema(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO conversations (id, created_at)
                VALUES
                    ('with-messages', '2026-01-01 09:00:00'),
                    ('without-messages', '2026-01-02 10:00:00')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO messages (conversation_id, created_at)
                VALUES
                    ('with-messages', '2026-01-01 09:30:00'),
                    ('with-messages', '2026-01-01 10:45:00')
                """
            )
        )

    ensure_conversation_last_message_at(engine)

    inspector = inspect(engine)
    assert "last_message_at" in {
        column["name"] for column in inspector.get_columns("conversations")
    }
    assert "ix_conversations_last_message_at" in {
        index["name"] for index in inspector.get_indexes("conversations")
    }
    with engine.connect() as connection:
        rows = dict(
            connection.execute(
                text("SELECT id, last_message_at FROM conversations")
            ).all()
        )
        null_count = connection.execute(
            text(
                "SELECT COUNT(*) FROM conversations "
                "WHERE last_message_at IS NULL"
            )
        ).scalar_one()
    assert rows == {
        "with-messages": "2026-01-01 10:45:00",
        "without-messages": "2026-01-02 10:00:00",
    }
    assert null_count == 0


def test_conversation_last_message_at_migration_is_idempotent():
    engine = create_engine("sqlite://")
    _create_legacy_schema(engine)

    ensure_conversation_last_message_at(engine)
    ensure_conversation_last_message_at(engine)

    inspector = inspect(engine)
    assert [
        column["name"]
        for column in inspector.get_columns("conversations")
        if column["name"] == "last_message_at"
    ] == ["last_message_at"]
    assert [
        index["name"]
        for index in inspector.get_indexes("conversations")
        if index["name"] == "ix_conversations_last_message_at"
    ] == ["ix_conversations_last_message_at"]


def test_sqlite_concurrent_migrations_both_succeed(tmp_path):
    database_path = tmp_path / "concurrent-migration.db"
    database_url = f"sqlite:///{database_path}"
    setup_engine = create_engine(database_url)
    _create_legacy_schema(setup_engine)
    with setup_engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO conversations (id, created_at)
                VALUES ('conversation-1', '2026-01-01 09:00:00')
                """
            )
        )
    setup_engine.dispose()

    engines = [
        create_engine(database_url, connect_args={"timeout": 10}),
        create_engine(database_url, connect_args={"timeout": 10}),
    ]
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(ensure_conversation_last_message_at, engines)
            )
        assert results == [None, None]

        inspector = inspect(engines[0])
        assert "last_message_at" in {
            column["name"] for column in inspector.get_columns("conversations")
        }
        assert "ix_conversations_last_message_at" in {
            index["name"] for index in inspector.get_indexes("conversations")
        }
        with engines[0].connect() as connection:
            assert connection.execute(
                text(
                    "SELECT last_message_at FROM conversations "
                    "WHERE id = 'conversation-1'"
                )
            ).scalar_one() == "2026-01-01 09:00:00"
            trigger_names = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type = 'trigger'"
                    )
                )
            }
        assert trigger_names == {
            "trg_conversations_last_message_at_not_null_insert",
            "trg_conversations_last_message_at_not_null_update",
        }
    finally:
        for engine in engines:
            engine.dispose()


def test_sqlite_migration_rejects_direct_null_insert_and_update():
    engine = create_engine("sqlite://")
    _create_legacy_schema(engine)
    ensure_conversation_last_message_at(engine)

    with pytest.raises(IntegrityError, match="last_message_at must not be null"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO conversations (id, created_at, last_message_at)
                    VALUES ('null-insert', '2026-01-01 09:00:00', NULL)
                    """
                )
            )

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO conversations (id, created_at, last_message_at)
                VALUES (
                    'null-update',
                    '2026-01-01 09:00:00',
                    '2026-01-01 09:00:00'
                )
                """
            )
        )
    with pytest.raises(IntegrityError, match="last_message_at must not be null"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE conversations SET last_message_at = NULL "
                    "WHERE id = 'null-update'"
                )
            )


def test_lifespan_propagates_migration_failure_after_create_all_succeeds(monkeypatch):
    engine = object()
    monkeypatch.setattr(main_module, "get_engine", lambda: engine)
    monkeypatch.setattr(
        main_module.Base.metadata, "create_all", lambda bind: None
    )
    monkeypatch.setattr(
        main_module,
        "ensure_conversation_last_message_at",
        lambda engine: (_ for _ in ()).throw(RuntimeError("migration failed")),
    )

    async def run_lifespan():
        async with main_module.lifespan(main_module.app):
            pass

    with pytest.raises(RuntimeError, match="migration failed"):
        asyncio.run(run_lifespan())


class _PostgresInspector:
    def has_table(self, table_name):
        return table_name in {"conversations", "messages"}

    def get_columns(self, table_name):
        return [{"name": "id"}, {"name": "created_at"}]

    def get_indexes(self, table_name):
        return []


class _PostgresConnection:
    def __init__(self, events):
        self.events = events

    def execute(self, statement):
        sql = " ".join(str(statement).split())
        self.events.append(("execute", sql))
        if sql.startswith("SELECT COUNT(*)"):
            return _ScalarResult(0)


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _PostgresEngine:
    class _Dialect:
        name = "postgresql"

    dialect = _Dialect()

    def __init__(self, events):
        self.events = events
        self.connection = _PostgresConnection(events)

    @contextmanager
    def begin(self):
        self.events.append(("begin", None))
        yield self.connection


def test_postgres_migration_locks_then_reinspects_and_uses_safe_ddl(monkeypatch):
    events = []
    engine = _PostgresEngine(events)

    def fake_inspect(bind):
        events.append(("inspect", bind))
        return _PostgresInspector()

    monkeypatch.setattr(schema_migrations, "inspect", fake_inspect)

    ensure_conversation_last_message_at(engine)

    assert events[0] == ("begin", None)
    assert events[1][0] == "execute"
    assert "pg_advisory_xact_lock" in events[1][1]
    assert events[2] == ("inspect", engine.connection)
    executed_sql = [sql for event, sql in events if event == "execute"]
    assert any("ADD COLUMN IF NOT EXISTS last_message_at" in sql for sql in executed_sql)
    assert any("ALTER COLUMN last_message_at SET NOT NULL" in sql for sql in executed_sql)
    assert any("CREATE INDEX IF NOT EXISTS ix_conversations_last_message_at" in sql for sql in executed_sql)
