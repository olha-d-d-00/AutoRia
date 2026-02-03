import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "autoria")
DB_USER = os.getenv("DB_USER", "autoria")
DB_PASSWORD = os.getenv("DB_PASSWORD", "autoria")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

TZ = os.getenv("TZ", "Europe/Kyiv")
SCRAPE_TIME = os.getenv("SCRAPE_TIME", "12:00")
DUMP_TIME = os.getenv("DUMP_TIME", "12:05")