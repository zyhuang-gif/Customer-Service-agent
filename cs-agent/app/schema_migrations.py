from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_conversation_last_message_at(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("conversations"):
        return

    column_names = {
        column["name"] for column in inspector.get_columns("conversations")
    }
    messages_exist = inspector.has_table("messages")

    with engine.begin() as connection:
        if "last_message_at" not in column_names:
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

        index_names = {
            index["name"] for index in inspect(connection).get_indexes("conversations")
        }
        if "ix_conversations_last_message_at" not in index_names:
            connection.execute(
                text(
                    "CREATE INDEX ix_conversations_last_message_at "
                    "ON conversations (last_message_at)"
                )
            )
