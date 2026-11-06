import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.environ.get("JOBTRACK_SECRET_KEY")
    DATABASE = BASE_DIR / "instance" / "jobtrack.db"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"