import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR / 'inventory.db'}")
SECRET_KEY = os.environ.get("SECRET_KEY", "")
HTTPS_ONLY = os.environ.get("HTTPS_ONLY", "0") == "1"
CHANDE_URL = os.environ.get(
    "CHANDE_URL",
    "https://chande.net/api/v1/prices/current",
)
PRICE_REFRESH_HOURS = int(os.environ.get("PRICE_REFRESH_HOURS", "1"))
