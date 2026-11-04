from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "LinkNest"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = "sqlite:///./linknest.db"
    BASE_URL: str = "http://localhost:8000"
    CODE_LENGTH: int = 6
    MAX_RETRY_COLLISIONS: int = 5

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
