from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 默认本地 Postgres；docker-compose 会用环境变量覆盖
    # psycopg2 在 Python 3.14 无预编译 wheel，改用 psycopg3（驱动名 psycopg）
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/cs"
    db_schema: str = "biz"


settings = Settings()
