import os
import time

import psycopg
from psycopg.rows import dict_row

SCHEMA = """
CREATE TABLE IF NOT EXISTS intake_batches (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    status TEXT NOT NULL,
    accepted_count INTEGER NOT NULL,
    rejected_count INTEGER NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS landed_rows (
    id BIGSERIAL PRIMARY KEY,
    batch_id BIGINT NOT NULL REFERENCES intake_batches(id),
    line_no INTEGER NOT NULL,
    station_code TEXT NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    tide_cm INTEGER NOT NULL,
    quality_flag TEXT NOT NULL,
    UNIQUE (station_code, observed_at)
);

CREATE TABLE IF NOT EXISTS reject_rows (
    id BIGSERIAL PRIMARY KEY,
    batch_id BIGINT NOT NULL REFERENCES intake_batches(id),
    line_no INTEGER NOT NULL,
    raw_line TEXT NOT NULL,
    reason TEXT NOT NULL
);
"""

SEED_CLEAN = """吴淞口 11-12 早班
WG01|202611120830|186|A
WG01|202611120900|191|A
BG02|202611120830|142|M
"""

SEED_BROKEN = """外高桥 11-12 错报
LG04|202611121000|205|A
WG01|202611120830|186|A
WG0X|202611121000|10|A
"""


def connect():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def init_db():
    last_error = None
    for _ in range(30):
        try:
            with connect() as conn:
                conn.execute(SCHEMA)
                count = conn.execute("SELECT COUNT(*) AS n FROM intake_batches").fetchone()["n"]
                if count == 0:
                    _seed(conn)
                conn.commit()
            return
        except psycopg.OperationalError as exc:
            last_error = exc
            time.sleep(1)
    raise last_error


def _insert_batch(conn, title: str, raw_text: str, created_by: str):
    from parser import parse_telegram_line

    batch = conn.execute(
        """
        INSERT INTO intake_batches (title, raw_text, status, accepted_count, rejected_count, created_by)
        VALUES (%s, %s, '处理中', 0, 0, %s)
        RETURNING id
        """,
        (title, raw_text, created_by),
    ).fetchone()
    accepted = 0
    rejected = 0
    seen = set()
    for line_no, raw_line in enumerate(raw_text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        parsed, reason = parse_telegram_line(raw_line)
        if reason:
            conn.execute(
                "INSERT INTO reject_rows (batch_id, line_no, raw_line, reason) VALUES (%s, %s, %s, %s)",
                (batch["id"], line_no, raw_line.strip(), reason),
            )
            rejected += 1
            continue
        key = (parsed["station_code"], parsed["observed_at"])
        if key in seen:
            reason = "同一批里观测时刻重复"
        else:
            existing = conn.execute(
                "SELECT id FROM landed_rows WHERE station_code = %s AND observed_at = %s",
                key,
            ).fetchone()
            reason = "这个站这个时刻已经落过库" if existing else None
        if reason:
            conn.execute(
                "INSERT INTO reject_rows (batch_id, line_no, raw_line, reason) VALUES (%s, %s, %s, %s)",
                (batch["id"], line_no, raw_line.strip(), reason),
            )
            rejected += 1
            continue
        seen.add(key)
        conn.execute(
            """
            INSERT INTO landed_rows (batch_id, line_no, station_code, observed_at, tide_cm, quality_flag)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                batch["id"],
                line_no,
                parsed["station_code"],
                parsed["observed_at"],
                parsed["tide_cm"],
                parsed["quality_flag"],
            ),
        )
        accepted += 1
    if accepted and not rejected:
        status = "已归集"
    elif accepted:
        status = "部分接纳"
    else:
        status = "未接纳"
    conn.execute(
        """
        UPDATE intake_batches
        SET status = %s, accepted_count = %s, rejected_count = %s
        WHERE id = %s
        """,
        (status, accepted, rejected, batch["id"]),
    )
    return batch["id"]


def _seed(conn):
    title, _, body = SEED_CLEAN.partition("\n")
    _insert_batch(conn, title, body.strip(), "admin")
    title, _, body = SEED_BROKEN.partition("\n")
    _insert_batch(conn, title, body.strip(), "admin")
