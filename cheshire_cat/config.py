"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = "postgresql+psycopg://cat:meow@localhost:5432/cheshire_cat"
    data_dir: Path = Path("data")
    sec_user_agent: str = "cheshire-cat/0.1 contact@example.com"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=os.getenv("CHESHIRE_CAT_DATABASE_URL", cls.database_url),
            data_dir=Path(os.getenv("CHESHIRE_CAT_DATA_DIR", str(cls.data_dir))),
            sec_user_agent=os.getenv("SEC_USER_AGENT", cls.sec_user_agent),
        )

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"


settings = Settings.from_env()
