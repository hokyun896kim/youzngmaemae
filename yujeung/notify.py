"""알림 문구 생성·기록. 발송은 하지 않는다 (사이트의 '오늘 볼 것'이 알림 역할).
모든 문구 맨 앞에 [작업명 #순번] 소주제 헤더를 붙인다 (순번 = notifications.seq)."""
from __future__ import annotations

import sqlite3

from . import db
from .config import JOB_NAME


def header(seq: int, topic: str) -> str:
    return f"[{JOB_NAME} #{seq}] {topic}"


def record(conn: sqlite3.Connection, topic: str, body: str, dedup_key: str | None = None) -> str | None:
    """헤더를 붙인 알림 문구를 만들어 기록하고 반환. dedup_key 가 이미 있으면 None."""
    if dedup_key and conn.execute("SELECT 1 FROM notifications WHERE dedup_key=?", (dedup_key,)).fetchone():
        return None
    cur = conn.execute(
        "INSERT INTO notifications (topic, dedup_key, text, sent_at) VALUES (?,?,?,?)",
        (topic, dedup_key, "", db.now()),
    )
    text = f"{header(cur.lastrowid, topic)}\n{body}"
    conn.execute("UPDATE notifications SET text=? WHERE seq=?", (text, cur.lastrowid))
    conn.commit()
    return text
