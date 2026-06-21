"""Application configuration via pydantic-settings."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Ollama / LLM ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3"

    # --- FastAPI ---
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # --- YouTube Data API v3 (AI-Times) ---
    youtube_api_key: str = ""

    # --- Gmail OAuth 2.0 (Mailman) ---
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_token_file: str = "tokens/gmail_token.json"
    gmail_credentials_file: str = "credentials/gmail_credentials.json"
    gmail_key_people: str = ""  # comma-separated

    @property
    def key_people_list(self) -> list[str]:
        return [p.strip() for p in self.gmail_key_people.split(",") if p.strip()]

    # --- Yahoo Finance (Wallstreet Wolf) ---
    stock_watchlist: str = "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,JPM,V,JNJ,WMT,PG,UNH,HD,MA,DIS,PYPL,NFLX,ADBE,CRM,INTC,AMD"

    @property
    def watchlist_tickers(self) -> list[str]:
        return [t.strip() for t in self.stock_watchlist.split(",") if t.strip()]

    # --- News API (News Briefer) ---
    newsapi_key: str = ""
    news_categories: str = "technology,business,science"
    news_country: str = "us"
    news_articles_count: int = 10

    @property
    def news_categories_list(self) -> list[str]:
        return [c.strip() for c in self.news_categories.split(",") if c.strip()]

    # --- Email Sending (SMTP) ---
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""

    # --- Scheduling ---
    schedule_ai_times: str = "08:00"
    schedule_mailman: str = "09:00"
    schedule_wallstreet: str = "07:30"
    schedule_news: str = "08:30"

    # --- Monitoring ---
    alarm_cpu_threshold: int = 90
    alarm_ram_threshold: int = 90
    alarm_disk_threshold: int = 90

    # --- Database ---
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'platform.db'}"

    # --- RAG Agent (DocVault) ---
    rag_folder_path: str = "./documents"
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    rag_top_k: int = 5


settings = Settings()
