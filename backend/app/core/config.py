from pydantic_settings import BaseSettings
from typing import List
import json

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7天
    ANTHROPIC_API_KEY: str = ""
    APP_ENV: str = "development"
    CORS_ORIGINS: str = '["http://localhost:5173"]'

    @property
    def cors_origins_list(self) -> List[str]:
        """支持 JSON 数组格式或逗号分隔字符串两种格式"""
        value = self.CORS_ORIGINS.strip()
        # 尝试 JSON 解析
        if value.startswith("["):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        # 逗号分隔字符串格式
        return [origin.strip() for origin in value.split(",") if origin.strip()]

    @property
    def async_database_url(self) -> str:
        """将 postgresql:// 自动转换为 postgresql+asyncpg:// 以支持异步驱动"""
        url = self.DATABASE_URL
        if url.startswith("postgresql://") or url.startswith("postgres://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
