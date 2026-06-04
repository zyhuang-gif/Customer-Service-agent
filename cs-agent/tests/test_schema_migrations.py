from sqlalchemy import create_engine, inspect, text

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
    assert rows == {
        "with-messages": "2026-01-01 10:45:00",
        "without-messages": "2026-01-02 10:00:00",
    }


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
