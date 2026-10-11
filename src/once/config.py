"""Runtime configuration, loaded from the environment (and .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RUNS_DIR = ROOT / "runs"

load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    neatlogs_api_key: str | None
    neatlogs_token: str | None
    neatlogs_project_id: str | None
    neatlogs_app_url: str
    llm_base_url: str | None
    llm_api_key: str | None
    model: str | None
    judge_model: str | None
    kb_base_url: str
    db_path: Path
    today: date

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_api_key and self.model)


def _env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def load() -> Settings:
    today = _env("ONCE_TODAY")
    return Settings(
        neatlogs_api_key=_env("NEATLOGS_API_KEY"),
        neatlogs_token=_env("NEATLOGS_TOKEN"),
        neatlogs_project_id=_env("NEATLOGS_PROJECT_ID"),
        neatlogs_app_url=(_env("NEATLOGS_APP_URL") or "https://app.neatlogs.com").rstrip("/"),
        llm_base_url=_env("LLM_BASE_URL"),
        llm_api_key=_env("LLM_API_KEY"),
        model=_env("ONCE_MODEL"),
        judge_model=_env("ONCE_JUDGE_MODEL") or _env("ONCE_MODEL"),
        kb_base_url=(_env("ONCE_KB_URL") or "https://neatlogs.github.io/support-copilot-demo-kb").rstrip("/"),
        db_path=Path(_env("ONCE_DB") or DATA_DIR / "once.db"),
        today=date.fromisoformat(today) if today else date.today(),
    )


settings = load()
