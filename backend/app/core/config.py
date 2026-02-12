from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置"""
    # SecondMe OAuth2
    SECONDME_CLIENT_ID: str = ""
    SECONDME_CLIENT_SECRET: str = ""
    SECONDME_REDIRECT_URI: str = "http://localhost:3000/api/auth/callback"
    SECONDME_AUTH_URL: str = "https://go.second.me/oauth/"
    SECONDME_API_BASE: str = "https://app.mindos.com"

    # Database
    DATABASE_URL: str = "sqlite:///./clawthon.db"

    # Security
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Backend
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"

    # CORS
    CORS_ORIGINS: list = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "https://clawthon-towow.vercel.app",
        "https://www.clawthon.xyz",
        "https://clawthon.xyz",
    ]

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
