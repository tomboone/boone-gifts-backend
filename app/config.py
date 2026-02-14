from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "mysql+pymysql://user:password@mysql_db:3306/boone_gifts"
    test_database_url: str = "mysql+pymysql://user:password@mysql_db:3306/boone_gifts_test"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = {"env_prefix": "APP_", "env_file": ".env"}


settings = Settings()
