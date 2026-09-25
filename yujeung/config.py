"""환경변수 기반 설정. GitHub Actions 에선 Secrets, 로컬에선 .env 로 넣는다."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 알림 헤더의 [작업명 #순번] 에 들어갈 작업명
JOB_NAME = "유증수집"

DATA_DIR = ROOT / "data"
DUMP_PATH = DATA_DIR / "yujeung.sql"          # git 에 커밋되는 원본 (텍스트 덤프)
SITE_JSON = DATA_DIR / "site.json"            # index.html 이 읽는 파일


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    dart_api_key: str
    krx_api_key: str
    telegram_token: str
    telegram_chat_id: str
    db_path: Path
    gap_alert_pct: float      # |괴리율| 이 이 이상이면 알림

    @classmethod
    def load(cls) -> "Config":
        _load_dotenv(ROOT / ".env")
        return cls(
            dart_api_key=os.environ.get("DART_API_KEY", ""),
            krx_api_key=os.environ.get("KRX_API_KEY", ""),
            telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
            db_path=Path(os.environ.get("YUJEUNG_DB", DATA_DIR / "yujeung.sqlite3")),
            gap_alert_pct=float(os.environ.get("GAP_ALERT_PCT", "20")),
        )
