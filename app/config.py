from typing import List
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "Ecommerce Analytics Platform"
    VERSION: str = '1.0.0'
    DEBUG: bool = False
    SECRET_KEY: str
    ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    DATABASE_URL: str
    MONGODB_DB: str = "ecommerce_raw"  
    SHOPIFY_API_VERSION: str = "2024-01" 
    AMAZON_SP_API_VERSION: str = "2023-09"  
    MONGODB_URL: str
    ENABLE_CACHE: bool = True
    ENABLE_BACKGROUND_SYNC: bool = True  
    ECHO_SQL: bool = False
    REDIS_URL: str
    RATE_LIMIT_PER_MINUTE: int = 60
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000", "http://127.0.0.1:3000"]

    class Config:
        env_file = '.env'
        case_sensitive = True
        extra = 'ignore'


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
