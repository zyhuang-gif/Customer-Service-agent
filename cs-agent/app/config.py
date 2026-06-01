from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    business_base_url: str = "http://localhost:8100"

    dashscope_api_key: str = ""  # 默认 key，下面各项缺省回落到它
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v4"
    rerank_model: str = "qwen3-rerank"
    chat_model: str = "qwen3-max"
    # 按模型分开授权的 key（百炼可对不同模型签发不同 key）；留空则回落到 dashscope_api_key
    embedding_api_key: str = ""
    rerank_api_key: str = ""
    chat_api_key: str = ""

    retrieve_top_n: int = 10
    retrieve_top_k: int = 3

    chroma_dir: str = "./chroma_db"
    knowledge_dir: str = "./app/knowledge"

    # HTTP 客户端
    business_timeout: float = 3.0
    business_retries: int = 1

    def key_for_embedding(self) -> str:
        return self.embedding_api_key or self.dashscope_api_key

    def key_for_rerank(self) -> str:
        return self.rerank_api_key or self.dashscope_api_key

    def key_for_chat(self) -> str:
        return self.chat_api_key or self.dashscope_api_key


settings = Settings()
