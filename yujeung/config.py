"""환경변수 기반 설정. .env 파일이 있으면 읽는다(외부 패키지 없이)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 알림 헤더의 [작업명 #순번] 에 들어갈 작업명
JOB_NAME = "유증수집"


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
    krx_id: str
    krx_pw: str
    telegram_token: str
    telegram_chat_id: str
    db_path: Path
    # 검증 필요: 신주인수권증서 시세를 주는 KRX 화면(bld). `verify` 로 확인 후 확정.
    krx_rights_bld: str
    # 괴리율 알림 임계값 (인수권 종가가 이론가 대비 이만큼 이상 싸거나 비쌀 때)
    gap_alert_pct: float

    @classmethod
    def load(cls) -> "Config":
        _load_dotenv(ROOT / ".env")
        return cls(
            dart_api_key=os.environ.get("DART_API_KEY", ""),
            krx_id=os.environ.get("KRX_ID", ""),
            krx_pw=os.environ.get("KRX_PW", ""),
            telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
            db_path=Path(os.environ.get("YUJEUNG_DB", ROOT / "data" / "yujeung.sqlite3")),
            krx_rights_bld=os.environ.get("KRX_RIGHTS_BLD", "dbms/MDC/STAT/standard/MDCSTAT01701"),
            gap_alert_pct=float(os.environ.get("GAP_ALERT_PCT", "20")),
        )
