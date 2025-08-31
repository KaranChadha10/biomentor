# app/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
print(f"[CONFIG] Loading .env from: {ENV_PATH}")
load_dotenv(dotenv_path=ENV_PATH)

class Settings:
    DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "biomentor")
    DB_USER = os.getenv("DB_USER", "biomentor")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "biomentor_pwd")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

settings = Settings()
print(f"[CONFIG] Loaded host={settings.DB_HOST} port={settings.DB_PORT} db={settings.DB_NAME} user={settings.DB_USER}")
