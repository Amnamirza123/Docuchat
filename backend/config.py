from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    google_api_key: str = ""
    embedding_model: str = "models/gemini-embedding-001"

    openrouter_api_key: str = ""
    openrouter_models: str = "nvidia/llama-3.1-nemotron-70b-instruct:free"

    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 75
    retrieval_top_k: int = 6

    allowed_origins: str = "http://localhost:5173"

    class Config:
        env_file = ".env"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def openrouter_models_list(self) -> list[str]:
        return [m.strip() for m in self.openrouter_models.split(",")]


settings = Settings()