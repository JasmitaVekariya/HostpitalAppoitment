import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# Get the absolute path of the backend directory containing this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/hospital_db"
    JWT_SECRET: str = "your_super_secret_jwt_key_here"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "google/gemma-4-31b-it:free"
    LLM_PROVIDER: str = "openrouter"  # openrouter, ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:3b"
    EMAIL_USER: Optional[str] = None
    EMAIL_PASSWORD: Optional[str] = None
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    BOOKING_BUFFER_MINUTES: int = 120
    FRONTEND_URL: str = "http://localhost:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        """Convert comma-separated CORS_ORIGINS string into a list of clean URLs."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # Load environment variables from the absolute path of .env
    model_config = SettingsConfigDict(env_file=ENV_PATH, extra="ignore")

settings = Settings()
