from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_conversation_last_message_at(engine: Engine) -> None:
    is_postgres = engine.dialect.name == "postgresql"

    with engine.begin() as connection:
        if is_postgres:
            connection.execute(
                text(
                    "SELECT pg_advisory_xact_lock("
                    "hashtext('cs_agent_conversation_last_message_at'))"
                )
            )

        inspector = inspect(connection)
        if not inspector.has_table("conversations"):
            return

        column_names = {
            column["name"] for column in inspector.get_columns("conversations")
        }
        messages_exist = inspector.has_table("messages")
        if "last_message_at" not in column_names:
            if is_postgres:
                connection.execute(
                    text(
                        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS "
                        "last_message_at TIMESTAMP"
                    )
                )
            else:
                connection.execute(
                    text(
                        "ALTER TABLE conversations "
                        "ADD COLUMN last_message_at TIMESTAMP"
                    )
                )

        if messages_exist:
            connection.execute(
                text(
                    """
                    UPDATE conversations
                    SET last_message_at = COALESCE(
                        (
                            SELECT MAX(messages.created_at)
                            FROM messages
                            WHERE messages.conversation_id = conversations.id
                        ),
                        created_at
                    )
                    WHERE last_message_at IS NULL
                    """
                )
            )
        else:
            connection.execute(
                text(
                    """
                    UPDATE conversations
                    SET last_message_at = created_at
                    WHERE last_message_at IS NULL
                    """
                )
            )

        null_count = connection.execute(
            text(
                "SELECT COUNT(*) FROM conversations "
                "WHERE last_message_at IS NULL"
            )
        ).scalar_one()
        if null_count:
            raise RuntimeError(
                "conversation last_message_at migration left NULL values"
            )

        if is_postgres:
            connection.execute(
                text(
                    "ALTER TABLE conversations "
                    "ALTER COLUMN last_message_at SET NOT NULL"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_conversations_last_message_at "
                    "ON conversations (last_message_at)"
                )
            )
        else:
            index_names = {
                index["name"]
                for index in inspect(connection).get_indexes("conversations")
            }
            if "ix_conversations_last_message_at" not in index_names:
                connection.execute(
                    text(
                        "CREATE INDEX ix_conversations_last_message_at "
                        "ON conversations (last_message_at)"
                    )
                )
