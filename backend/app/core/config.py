"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings

# Repository root, anchored to this file so the .env file is found no matter
# what the current working directory is: backend/app/core/config.py -> core
# -> app -> backend -> SQLense
REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    APP_NAME: str = "SQLense"
    APP_ENV: str = "development"
    DEBUG: bool = True

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    GROQ_API_KEY: str = ""
    DATABASE_URL: str = ""
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    class Config:
        env_file = str(REPO_ROOT / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
