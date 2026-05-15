"""
配置加载
========
- 用 pydantic-settings 从 .env 加载，类型校验、默认值、IDE 提示一并搞定
- 任何配置项都走这个 settings 单例，绝不在代码里硬编码
"""

from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 鉴权
    SECRET_KEY: str = "dev-secret-please-change-in-prod"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 默认 7 天
    JWT_ALGORITHM: str = "HS256"

    # 数据库
    DATABASE_URL: str = "sqlite:///./app.db"

    # LLM Provider API Keys（Day 2 启用）
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""

    # 可选: mock / deepseek / claude / openai / gemini
    DEFAULT_LLM_PROVIDER: str = "deepseek"
    DEFAULT_CLAUDE_MODEL: str = "claude-opus-4-7"
    DEFAULT_DEEPSEEK_MODEL: str = "deepseek-chat"

    # CORS
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()
