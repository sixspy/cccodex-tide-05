from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from auth import authenticate, issue_token, read_user
from db import (
    ST_PENDING,
    connect,
    create_pending_batch,
    get_today_policy,
    init_db,
    run_comparison,
    set_today_policy,
    update_batch_decision,
)
from dedup import DECISIONS
from parser import FLAGS


class LoginBody(BaseModel):
    username: str
    password: str


class BatchBody(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    raw_text: str = Field(min_length=1)


class DecisionBody(BaseModel):
    decision: str


def _stamp(value):
    return value.isoformat(sep=" ", timespec="minutes") if value else None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


def _user_or_401(authorization: str | None):
    user = read_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


def _writer_or_403(user):
    if user["role"] != "writer":
        raise HTTPException(status_code=403, detail="档案员不能归集报文")


def _serialise_batch(batch):
    batch["created_at"] = _stamp(batch["created_at"])
    if batch.get("policy_created_at"):
        batch["policy_created_at"] = _stamp(batch["policy_created_at"])
    return batch


@app.get("/api/health")
def health():
    with connect() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok", "service": "tide-telegram-intake"}


@app.post("/api/login")
def login(body: LoginBody):
    user = authenticate(body.username.strip(), body.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {
        "access_token": issue_token(user),
        "username": user["username"],
        "role": user["role"],
        "title": user["title"],
    }


@app.get("/api/policy")
def today_policy(authorization: str | None = Header(default=None)):
    """当日策略簿：返回今日取舍及是否已锁定。"""
    _user_or_401(authorization)
    with connect() as conn:
        policy = get_today_policy(conn)
    if not policy:
        return {"policy_date": None, "decision": None, "locked": False,
                "options": list(DECISIONS)}
    return {
        "policy_date": policy["policy_date"].isoformat(),
        "decision": policy["decision"],
        "created_by": policy["created_by"],
        "created_at": _stamp(policy["created_at"]),
        "locked": True,  # 写入当日即锁定，禁止改口
        "options": list(DECISIONS),
    }


@app.post("/api/policy")
def write_policy(body: DecisionBody, authorization: str | None = Header(default=None)):
    user = _user_or_401(authorization)
    _writer_or_403(user)
    if body.decision not in DECISIONS:
        raise HTTPException(status_code=400, detail="取舍只能是「留行」或「双拒」")
    with connect() as conn:
        try:
            policy = set_today_policy(conn, body.decision, user["username"])
            conn.commit()
        except RuntimeError as exc:
            conn.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "policy_date": policy["policy_date"].isoformat(),
        "decision": policy["decision"],
        "created_by": policy["created_by"],
        "created_at": _stamp(policy["created_at"]),
        "locked": True,
        "options": list(DECISIONS),
    }


@app.get("/api/batches")
def list_batches(authorization: str | None = Header(default=None)):
    """批内列表：保留行号、跳过行号、取舍名一并给出。"""
    _user_or_401(authorization)
    with connect() as conn:
        batches = conn.execute(
            """
            SELECT b.id, b.title, b.status, b.decision, b.decision_mismatch,
                   b.accepted_count, b.rejected_count, b.skipped_count,
                   b.locked_by_batch_id, b.created_by, b.created_at,
                   p.decision AS policy_decision
            FROM intake_batches b
            LEFT JOIN policy_book p ON p.policy_date = (b.created_at AT TIME ZONE 'Asia/Shanghai')::date
            ORDER BY b.id DESC
            """
        ).fetchall()
        line_stats = conn.execute(
            """
            SELECT batch_id,
                   ARRAY_AGG(line_no) FILTER (
                       WHERE disposition IN ('保留落库', '已落库')
                   ) AS retained_lines
            FROM batch_rows
            GROUP BY batch_id
            """
        ).fetchall()
        skip_stats = conn.execute(
            """
            SELECT batch_id, ARRAY_AGG(line_no ORDER BY line_no) AS skip_lines
            FROM skip_queue GROUP BY batch_id
            """
        ).fetchall()
    stats = {row["batch_id"]: row for row in line_stats}
    skip_map = {row["batch_id"]: row["skip_lines"] for row in skip_stats}
    result = []
    for batch in batches:
        row = _serialise_batch(dict(batch))
        stat = stats.get(batch["id"], {})
        # 行号可能为 NULL（缺失行不参与比较），列表只展示有行号的
        row["retained_line_nos"] = [n for n in (stat.get("retained_lines") or []) if n is not None]
        row["skipped_line_nos"] = [n for n in skip_map.get(batch["id"], []) if n is not None]
        result.append(row)
    return result


@app.get("/api/batches/{batch_id}")
def batch_detail(batch_id: int, authorization: str | None = Header(default=None)):
    """行号详情：逐行给出去向，被跳过的行可点开看原文。"""
    _user_or_401(authorization)
    with connect() as conn:
        batch = conn.execute(
            """
            SELECT b.*, p.decision AS policy_decision
            FROM intake_batches b
            LEFT JOIN policy_book p
                ON p.policy_date = (b.created_at AT TIME ZONE 'Asia/Shanghai')::date
            WHERE b.id = %s
            """,
            (batch_id,),
        ).fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="没有这一批报文")
        rows = conn.execute(
            """
            SELECT line_no, raw_line, station_code, observed_at, tide_cm,
                   quality_flag, parse_reason, disposition
            FROM batch_rows WHERE batch_id = %s ORDER BY line_no NULLS LAST, id
            """,
            (batch_id,),
        ).fetchall()
        rejected = conn.execute(
            "SELECT line_no, raw_line, reason FROM reject_rows WHERE batch_id = %s ORDER BY line_no",
            (batch_id,),
        ).fetchall()
        skipped = conn.execute(
            """
            SELECT id, line_no, raw_line, station_code, observed_at, reason,
                   decision, kept_line_no
            FROM skip_queue WHERE batch_id = %s ORDER BY line_no NULLS LAST, id
            """,
            (batch_id,),
        ).fetchall()
        landed = conn.execute(
            """
            SELECT line_no, station_code, observed_at, tide_cm, quality_flag
            FROM landed_rows WHERE batch_id = %s ORDER BY line_no
            """,
            (batch_id,),
        ).fetchall()
        lock_rows = conn.execute(
            """
            SELECT lock_key, station_code, observed_at, holder_batch_id, blocked_batch_id
            FROM order_locks
            WHERE holder_batch_id = %s OR blocked_batch_id = %s
            ORDER BY lock_key
            """,
            (batch_id, batch_id),
        ).fetchall()
        holder_title = None
        if batch["locked_by_batch_id"]:
            holder = conn.execute(
                "SELECT title FROM intake_batches WHERE id = %s",
                (batch["locked_by_batch_id"],),
            ).fetchone()
            holder_title = holder["title"] if holder else None

    batch = _serialise_batch(dict(batch))
    for row in rows:
        if row["observed_at"]:
            row["observed_at"] = _stamp(row["observed_at"])
        if row["quality_flag"]:
            row["flag_label"] = FLAGS.get(row["quality_flag"], row["quality_flag"])
        # 被顺序锁拦截的批次没跑到去重，行去向统一显示「未比较」
        if batch["status"] == "顺序锁拦截" and not row["parse_reason"]:
            row["disposition"] = "未比较"
    for row in landed:
        row["observed_at"] = _stamp(row["observed_at"])
        row["flag_label"] = FLAGS.get(row["quality_flag"], row["quality_flag"])
    for row in skipped:
        row["observed_at"] = _stamp(row["observed_at"])
    for row in lock_rows:
        row["observed_at"] = _stamp(row["observed_at"])
    return {
        "batch": batch,
        "rows": rows,
        "landed": landed,
        "rejected": rejected,
        "skipped": skipped,
        "locks": lock_rows,
        "holder_batch_title": holder_title,
        "can_edit_settings": batch["status"] == ST_PENDING,
    }


@app.post("/api/batches")
def create_batch(body: BatchBody, authorization: str | None = Header(default=None)):
    """阶段一：贴入即解析，批次停在「待比较」，不动 landed_rows。"""
    user = _user_or_401(authorization)
    _writer_or_403(user)

    title = body.title.strip()
    raw_text = body.raw_text.strip()
    if not title or not raw_text:
        raise HTTPException(status_code=400, detail="标题和报文都不能空")
    with connect() as conn:
        policy = get_today_policy(conn)
        batch_id = create_pending_batch(conn, title, raw_text, user["username"])
        # 有策略簿时默认跟随当日取舍；没有则默认留行，等待比较前可改
        default_decision = policy["decision"] if policy else "留行"
        update_batch_decision(conn, batch_id, default_decision)
        conn.commit()
    return batch_detail(batch_id, authorization)


@app.put("/api/batches/{batch_id}/decision")
def set_batch_decision(batch_id: int, body: DecisionBody,
                       authorization: str | None = Header(default=None)):
    """批内设置：仅「待比较」阶段可改，比较开始即冻结。"""
    user = _user_or_401(authorization)
    _writer_or_403(user)
    if body.decision not in DECISIONS:
        raise HTTPException(status_code=400, detail="取舍只能是「留行」或「双拒」")
    with connect() as conn:
        try:
            update_batch_decision(conn, batch_id, body.decision)
            conn.commit()
        except KeyError as exc:
            conn.rollback()
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            conn.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return batch_detail(batch_id, authorization)


@app.post("/api/batches/{batch_id}/compare")
def compare_batch(batch_id: int, authorization: str | None = Header(default=None)):
    """阶段二：批内去重、顺序锁、跨批去重并落库，一个事务完成。"""
    user = _user_or_401(authorization)
    _writer_or_403(user)
    with connect() as conn:
        try:
            run_comparison(conn, batch_id)
            conn.commit()
        except KeyError as exc:
            conn.rollback()
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            conn.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return batch_detail(batch_id, authorization)


@app.get("/api/skips")
def skip_queue(authorization: str | None = Header(default=None)):
    """跳过队列：全站视角，含批内重行、双拒、跨批重复。"""
    _user_or_401(authorization)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.batch_id, b.title AS batch_title, s.line_no, s.raw_line,
                   s.station_code, s.observed_at, s.reason, s.decision, s.kept_line_no,
                   s.created_at
            FROM skip_queue s
            JOIN intake_batches b ON b.id = s.batch_id
            ORDER BY s.id DESC
            """
        ).fetchall()
    for row in rows:
        row["observed_at"] = _stamp(row["observed_at"])
        row["created_at"] = _stamp(row["created_at"])
    return rows


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
