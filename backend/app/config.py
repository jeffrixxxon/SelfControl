from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Telegram
    bot_token: str = ""
    webapp_url: str = ""  # https://your-domain.ru — адрес мини-аппа
    # Пусто = бот открыт для всех. Иначе список Telegram ID через запятую.
    allowed_user_ids: str = ""

    # База
    database_url: str = "sqlite+aiosqlite:///./selfcontrol.db"

    # Claude
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5-5"
    claude_max_tokens: int = 2048
    history_messages: int = 20

    # Голос: local (faster-whisper) | openai
    transcribe_provider: str = "local"
    whisper_model: str = "small"
    openai_api_key: str = ""

    # Значения по умолчанию для новых пользователей
    default_timezone: str = "Europe/Moscow"
    default_currency: str = "RUB"

    # Разработка: при DEBUG=true и DEV_TG_ID API работает без Telegram initData
    debug: bool = False
    dev_tg_id: int = 0

    @property
    def allowed_ids(self) -> set[int]:
        return {int(x) for x in self.allowed_user_ids.replace(" ", "").split(",") if x}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
