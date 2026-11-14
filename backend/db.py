import os
import time

import psycopg
from psycopg.rows import dict_row

from dedup import (
    DECISIONS,
    DISP_DOUBLE_REJECT,
    DISP_KEPT,
    DISP_SINGLE,
    DISP_SKIPPED_DUP,
    KEEP_FIRST,
    REJECT_BOTH,
    SKIP_ALREADY_LANDED,
    SKIP_DOUBLE_REJECT,
    SKIP_KEPT_ELSEWHERE,
    classify_rows,
)
from parser import parse_with_line_no

# 批次状态
ST_PENDING = "待比较"
ST_COMPARING = "比较中"
ST_DONE = "已归集"
ST_PARTIAL = "部分接纳"
ST_NONE = "未接纳"
ST_LOCKED = "顺序锁拦截"
TERMINAL_STATES = (ST_DONE, ST_PARTIAL, ST_NONE, ST_LOCKED)

SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_book (
    id BIGSERIAL PRIMARY KEY,
    policy_date DATE NOT NULL UNIQUE,
    decision TEXT NOT NULL CHECK (decision IN ('留行', '双拒')),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS intake_batches (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    status TEXT NOT NULL,
    accepted_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    decision TEXT,
    decision_mismatch BOOLEAN NOT NULL DEFAULT FALSE,
    locked_by_batch_id BIGINT REFERENCES intake_batches(id),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS landed_rows (
    id BIGSERIAL PRIMARY KEY,
    batch_id BIGINT NOT NULL REFERENCES intake_batches(id),
    line_no INTEGER,
    station_code TEXT NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    tide_cm INTEGER NOT NULL,
    quality_flag TEXT NOT NULL,
    UNIQUE (station_code, observed_at)
);

CREATE TABLE IF NOT EXISTS reject_rows (
    id BIGSERIAL PRIMARY KEY,
    batch_id BIGINT NOT NULL REFERENCES intake_batches(id),
    line_no INTEGER,
    raw_line TEXT NOT NULL,
    reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS batch_rows (
    id BIGSERIAL PRIMARY KEY,
    batch_id BIGINT NOT NULL REFERENCES intake_batches(id),
    line_no INTEGER,
    raw_line TEXT NOT NULL,
    station_code TEXT,
    observed_at TIMESTAMP,
    tide_cm INTEGER,
    quality_flag TEXT,
    parse_reason TEXT,
    disposition TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skip_queue (
    id BIGSERIAL PRIMARY KEY,
    batch_id BIGINT NOT NULL REFERENCES intake_batches(id),
    line_no INTEGER,
    raw_line TEXT NOT NULL,
    station_code TEXT,
    observed_at TIMESTAMP,
    reason TEXT NOT NULL,
    decision TEXT,
    kept_line_no INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_locks (
    id BIGSERIAL PRIMARY KEY,
    lock_key TEXT NOT NULL UNIQUE,
    station_code TEXT NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    holder_batch_id BIGINT NOT NULL REFERENCES intake_batches(id),
    blocked_batch_id BIGINT REFERENCES intake_batches(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_batch_rows_batch ON batch_rows(batch_id);
-- 只有解析成功的行要求批内行号唯一；解析失败行（如显式行号重复）不参与约束
CREATE UNIQUE INDEX IF NOT EXISTS uq_batch_rows_valid_line
    ON batch_rows(batch_id, line_no) WHERE parse_reason IS NULL;
CREATE INDEX IF NOT EXISTS idx_skip_queue_batch ON skip_queue(batch_id);
CREATE INDEX IF NOT EXISTS idx_landed_lookup ON landed_rows(station_code, observed_at);
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

SEED_DUP = """堡镇 11-12 重行班
BZ03|202611120900|176|A
BZ03|202611120900|178|A
BZ03|202611121000|165|M
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


def get_today_policy(conn):
    return conn.execute(
        """
        SELECT id, policy_date, decision, created_by, created_at
        FROM policy_book WHERE policy_date = CURRENT_DATE
        """
    ).fetchone()


def set_today_policy(conn, decision: str, created_by: str):
    """写当日策略簿；当日已有记录即拒绝改口。"""
    if decision not in DECISIONS:
        raise ValueError(f"未知取舍: {decision!r}")
    existing = get_today_policy(conn)
    if existing:
        raise RuntimeError(
            f"今日策略簿已写为「{existing['decision']}」，当日禁止改口"
        )
    row = conn.execute(
        """
        INSERT INTO policy_book (policy_date, decision, created_by)
        VALUES (CURRENT_DATE, %s, %s)
        RETURNING id, policy_date, decision, created_by, created_at
        """,
        (decision, created_by),
    ).fetchone()
    return row


def create_pending_batch(conn, title: str, raw_text: str, created_by: str):
    """阶段一：贴入即解析，逐行落 batch_rows，批次停在「待比较」，不碰 landed_rows。"""
    batch = conn.execute(
        """
        INSERT INTO intake_batches (title, raw_text, status, created_by)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (title, raw_text, ST_PENDING, created_by),
    ).fetchone()
    batch_id = batch["id"]
    explicit_lines = set()

    for physical_no, raw_line in enumerate(raw_text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        segments = raw_line.strip().split("|")
        is_explicit = len(segments) == 5 and segments[0].strip() != "-"
        line_no, parsed, reason = parse_with_line_no(raw_line, physical_no)
        # 五段式显式行号在同批内重复：按解析失败记录，避免撞唯一约束
        if not reason and is_explicit and line_no in explicit_lines:
            reason = f"行号 {line_no} 在本批里重复"
            parsed = None
        if line_no is not None:
            explicit_lines.add(line_no)
        if reason:
            conn.execute(
                """
                INSERT INTO batch_rows
                    (batch_id, line_no, raw_line, parse_reason, disposition)
                VALUES (%s, %s, %s, %s, '解析失败')
                """,
                (batch_id, line_no, raw_line.strip(), reason),
            )
            conn.execute(
                "INSERT INTO reject_rows (batch_id, line_no, raw_line, reason) VALUES (%s, %s, %s, %s)",
                (batch_id, line_no, raw_line.strip(), reason),
            )
            continue
        conn.execute(
            """
            INSERT INTO batch_rows
                (batch_id, line_no, raw_line, station_code, observed_at,
                 tide_cm, quality_flag, parse_reason, disposition)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s)
            """,
            (
                batch_id,
                line_no,
                raw_line.strip(),
                parsed["station_code"],
                parsed["observed_at"],
                parsed["tide_cm"],
                parsed["quality_flag"],
                DISP_SINGLE,
            ),
        )
    return batch_id


def update_batch_decision(conn, batch_id: int, decision: str):
    """阶段一允许改批内设置；批次一旦离开「待比较」即禁止修改。"""
    if decision not in DECISIONS:
        raise ValueError(f"未知取舍: {decision!r}")
    batch = conn.execute(
        "SELECT status FROM intake_batches WHERE id = %s",
        (batch_id,),
    ).fetchone()
    if not batch:
        raise KeyError("没有这一批报文")
    if batch["status"] != ST_PENDING:
        raise RuntimeError(f"批次处于「{batch['status']}」，比较还没写完时不许改批内设置")
    policy = get_today_policy(conn)
    mismatch = bool(policy and policy["decision"] != decision)
    conn.execute(
        "UPDATE intake_batches SET decision = %s, decision_mismatch = %s WHERE id = %s",
        (decision, mismatch, batch_id),
    )


def _lock_key(station_code: str, observed_at) -> str:
    return f"{station_code}|{observed_at.strftime('%Y%m%d%H%M')}"


def run_comparison(conn, batch_id: int):
    """阶段二：批内去重 + 顺序锁 + 跨批去重，全部在一个事务里完成。

    返回最终状态字符串。顺序锁拦截时不做任何落库，只写 order_locks 审计
    与批次拦截状态，由调用方提交；咨询锁随事务结束自动释放。
    """
    import hashlib  # 局部导入，文件顶部保持依赖清爽

    batch = conn.execute(
        "SELECT id, status, decision FROM intake_batches WHERE id = %s",
        (batch_id,),
    ).fetchone()
    if not batch:
        raise KeyError("没有这一批报文")
    if batch["status"] != ST_PENDING:
        raise RuntimeError(f"批次处于「{batch['status']}」，不能再次比较")

    policy = get_today_policy(conn)
    decision = batch["decision"] or (policy["decision"] if policy else KEEP_FIRST)
    mismatch = bool(policy and policy["decision"] != decision)

    rows = conn.execute(
        """
        SELECT id, line_no, raw_line, station_code, observed_at, tide_cm,
               quality_flag, parse_reason, disposition
        FROM batch_rows WHERE batch_id = %s ORDER BY id
        """,
        (batch_id,),
    ).fetchall()

    valid_rows = [r for r in rows if not r["parse_reason"]]
    classified = classify_rows(valid_rows, decision)
    dispositions = classified["dispositions"]

    # 进入比较中：此后批内设置冻结
    conn.execute(
        "UPDATE intake_batches SET status = %s, decision = %s, decision_mismatch = %s WHERE id = %s",
        (ST_COMPARING, decision, mismatch, batch_id),
    )

    # ---- 顺序锁：对每个重行键按固定顺序加事务级咨询锁，避免交叉死锁 ----
    # 咨询锁只负责把并发批次串行化；order_locks 台账持久记住先到批次，
    # 因此后到事务拿到锁后仍能查到持有者，整批被拦。
    dup_keys = {}
    for group_indexes in classified["duplicate_groups"]:
        first = valid_rows[group_indexes[0]]
        dup_keys[_lock_key(first["station_code"], first["observed_at"])] = (
            first["station_code"],
            first["observed_at"],
        )

    blocked = None
    inserted_keys = []
    for key in sorted(dup_keys):
        station_code, observed_at = dup_keys[key]
        lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") >> 1
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (lock_id,))
        holder = conn.execute(
            "SELECT holder_batch_id FROM order_locks WHERE lock_key = %s",
            (key,),
        ).fetchone()
        if holder:
            blocked = (key, station_code, observed_at, holder["holder_batch_id"])
            break
        conn.execute(
            """
            INSERT INTO order_locks (lock_key, station_code, observed_at, holder_batch_id)
            VALUES (%s, %s, %s, %s)
            """,
            (key, station_code, observed_at, batch_id),
        )
        inserted_keys.append(key)

    if blocked:
        key, station_code, observed_at, holder_batch_id = blocked
        # 本批在被拦键之前抢占的其它键必须撤掉：整批既已拦截，
        # 不能留下幻影持锁行去误拦后续批次
        if inserted_keys:
            conn.execute(
                "DELETE FROM order_locks WHERE lock_key = ANY(%s)",
                (inserted_keys,),
            )
        conn.execute(
            "UPDATE order_locks SET blocked_batch_id = %s WHERE lock_key = %s",
            (batch_id, key),
        )
        # 整批拦截：不删解析失败记录，rejected_count 保留原值
        parse_failures = conn.execute(
            "SELECT COUNT(*) AS n FROM reject_rows WHERE batch_id = %s",
            (batch_id,),
        ).fetchone()["n"]
        conn.execute(
            """
            UPDATE intake_batches
            SET status = %s, locked_by_batch_id = %s,
                accepted_count = 0, rejected_count = %s, skipped_count = 0
            WHERE id = %s
            """,
            (ST_LOCKED, holder_batch_id, parse_failures, batch_id),
        )
        return ST_LOCKED

    # ---- 批内取舍写回 batch_rows / skip_queue ----
    accepted = 0
    skipped = 0
    rejected = conn.execute(
        "SELECT COUNT(*) AS n FROM reject_rows WHERE batch_id = %s",
        (batch_id,),
    ).fetchone()["n"]
    # 每个重行键对应的保留行号（留行取舍下即组内最小行号）
    kept_line_by_key = {
        (valid_rows[group[0]]["station_code"], valid_rows[group[0]]["observed_at"]):
            valid_rows[group[0]]["line_no"]
        for group in classified["duplicate_groups"]
    }

    for local_idx, row in enumerate(valid_rows):
        disp = dispositions[local_idx]
        conn.execute(
            "UPDATE batch_rows SET disposition = %s WHERE id = %s",
            (disp, row["id"]),
        )
        if disp == DISP_DOUBLE_REJECT:
            conn.execute(
                """
                INSERT INTO skip_queue
                    (batch_id, line_no, raw_line, station_code, observed_at,
                     reason, decision, kept_line_no)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
                """,
                (batch_id, row["line_no"], row["raw_line"], row["station_code"],
                 row["observed_at"], SKIP_DOUBLE_REJECT, decision),
            )
            skipped += 1
        elif disp == DISP_SKIPPED_DUP:
            kept_line_no = kept_line_by_key[(row["station_code"], row["observed_at"])]
            conn.execute(
                """
                INSERT INTO skip_queue
                    (batch_id, line_no, raw_line, station_code, observed_at,
                     reason, decision, kept_line_no)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (batch_id, row["line_no"], row["raw_line"], row["station_code"],
                 row["observed_at"], SKIP_KEPT_ELSEWHERE, decision, kept_line_no),
            )
            skipped += 1

    # ---- 跨批去重并落库（保留行与单行参与；双拒/跳过的不参与）----
    for local_idx, row in enumerate(valid_rows):
        disp = dispositions[local_idx]
        if disp in (DISP_DOUBLE_REJECT, DISP_SKIPPED_DUP):
            continue
        existing = conn.execute(
            "SELECT id FROM landed_rows WHERE station_code = %s AND observed_at = %s",
            (row["station_code"], row["observed_at"]),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE batch_rows SET disposition = '跨批重复' WHERE id = %s",
                (row["id"],)
            )
            conn.execute(
                """
                INSERT INTO skip_queue
                    (batch_id, line_no, raw_line, station_code, observed_at,
                     reason, decision, kept_line_no)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
                """,
                (batch_id, row["line_no"], row["raw_line"], row["station_code"],
                 row["observed_at"], SKIP_ALREADY_LANDED, decision),
            )
            skipped += 1
            continue
        conn.execute(
            """
            INSERT INTO landed_rows (batch_id, line_no, station_code, observed_at, tide_cm, quality_flag)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (batch_id, row["line_no"], row["station_code"], row["observed_at"],
             row["tide_cm"], row["quality_flag"]),
        )
        if disp == DISP_SINGLE:
            conn.execute(
                "UPDATE batch_rows SET disposition = '已落库' WHERE id = %s",
                (row["id"],)
            )
        else:  # DISP_KEPT
            conn.execute(
                "UPDATE batch_rows SET disposition = '保留落库' WHERE id = %s",
                (row["id"],)
            )
        accepted += 1

    # order_locks 台账行保留不删：它记录先到批次，后到的同键批次要据此被顺序锁拦截。
    # 咨询锁随事务结束自动释放。

    if accepted and not (rejected or skipped):
        status = ST_DONE
    elif accepted:
        status = ST_PARTIAL
    else:
        status = ST_NONE
    conn.execute(
        """
        UPDATE intake_batches
        SET status = %s, accepted_count = %s, rejected_count = %s, skipped_count = %s
        WHERE id = %s
        """,
        (status, accepted, rejected, skipped, batch_id),
    )
    return status


def _seed(conn):
    # 种子沿用留行取舍，并直接跑完比较，保证演示数据是终态
    set_today_policy(conn, KEEP_FIRST, "admin")
    for text in (SEED_CLEAN, SEED_BROKEN, SEED_DUP):
        title, _, body = text.partition("\n")
        batch_id = create_pending_batch(conn, title, body.strip(), "admin")
        update_batch_decision(conn, batch_id, KEEP_FIRST)
        run_comparison(conn, batch_id)
