"""The UnderCover database: one SQLite file, opened per request."""

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

DATA = Path(__file__).parents[1] / "data"
DEFAULT_PATH = Path(__file__).parent / "undercover.db"


def path() -> Path:
    """Return the database file, from UNDERCOVER_DB or the default."""
    return Path(os.environ.get("UNDERCOVER_DB", DEFAULT_PATH))


def connect() -> sqlite3.Connection:
    """Open a connection that returns rows by column name."""
    conn = sqlite3.connect(path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def load(name: str) -> list[dict[str, Any]]:
    """Read one of the JSON files in data/."""
    return json.loads((DATA / name).read_text())
