"""알림. 모든 메시지 맨 앞에 [작업명 #순번] 소주제 헤더를 붙인다 (순번 = notifications.seq)."""
from __future__ import annotations

import sqlite3

import requests

from . import db
from .config import JOB_NAME, Config


def header(seq: int, topic: str) -> str:
    return f"[{JOB_NAME} #{seq}] {topic}"


def send(conn: sqlite3.Connection, cfg: Config, topic: str, body: str, dedup_key: str | None = None,
         http_post=requests.post) -> str | None:
    """발송 후 최종 텍스트 반환. dedup_key 가 이미 있으면 보내지 않고 None.
    텔레그램 설정이 없으면 기록만 남기고 콘솔 출력 (Actions 로그에서 확인)."""
    if dedup_key and conn.execute("SELECT 1 FROM notifications WHERE dedup_key=?", (dedup_key,)).fetchone():
        return None
    cur = conn.execute(
        "INSERT INTO notifications (topic, dedup_key, text, sent_at, delivered) VALUES (?,?,?,?,0)",
        (topic, dedup_key, "", db.now()),
    )
    seq = cur.lastrowid
    text = f"{header(seq, topic)}\n{body}"
    delivered = 0
    if cfg.telegram_token and cfg.telegram_chat_id:
        try:
            resp = http_post(
                f"https://api.telegram.org/bot{cfg.telegram_token}/sendMessage",
                json={"chat_id": cfg.telegram_chat_id, "text": text, "disable_web_page_preview": True},
                timeout=15,
            )
            delivered = int(resp.ok)
        except requests.RequestException:
            delivered = 0
    print(text + ("" if delivered else "\n(텔레그램 미발송)"))
    conn.execute("UPDATE notifications SET text=?, delivered=? WHERE seq=?", (text, delivered, seq))
    conn.commit()
    return text
