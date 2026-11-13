from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from auth import authenticate, issue_token, read_user
from db import connect, init_db
from parser import FLAGS


class LoginBody(BaseModel):
    username: str
    password: str


class BatchBody(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    raw_text: str = Field(min_length=1)


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


@app.get("/api/batches")
def list_batches(authorization: str | None = Header(default=None)):
    _user_or_401(authorization)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, title, status, accepted_count, rejected_count, created_by, created_at
            FROM intake_batches
            ORDER BY id DESC
            """
        ).fetchall()
    for row in rows:
        row["created_at"] = _stamp(row["created_at"])
    return rows


@app.get("/api/batches/{batch_id}")
def batch_detail(batch_id: int, authorization: str | None = Header(default=None)):
    _user_or_401(authorization)
    with connect() as conn:
        batch = conn.execute(
            """
            SELECT id, title, raw_text, status, accepted_count, rejected_count, created_by, created_at
            FROM intake_batches WHERE id = %s
            """,
            (batch_id,),
        ).fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="没有这一批报文")
        landed = conn.execute(
            """
            SELECT line_no, station_code, observed_at, tide_cm, quality_flag
            FROM landed_rows WHERE batch_id = %s ORDER BY line_no
            """,
            (batch_id,),
        ).fetchall()
        rejected = conn.execute(
            """
            SELECT line_no, raw_line, reason
            FROM reject_rows WHERE batch_id = %s ORDER BY line_no
            """,
            (batch_id,),
        ).fetchall()
    batch["created_at"] = _stamp(batch["created_at"])
    for row in landed:
        row["observed_at"] = _stamp(row["observed_at"])
        row["flag_label"] = FLAGS.get(row["quality_flag"], row["quality_flag"])
    return {"batch": batch, "landed": landed, "rejected": rejected}


@app.post("/api/batches")
def create_batch(body: BatchBody, authorization: str | None = Header(default=None)):
    user = _user_or_401(authorization)
    if user["role"] != "writer":
        raise HTTPException(status_code=403, detail="档案员不能归集报文")
    from db import _insert_batch

    title = body.title.strip()
    raw_text = body.raw_text.strip()
    if not title or not raw_text:
        raise HTTPException(status_code=400, detail="标题和报文都不能空")
    with connect() as conn:
        batch_id = _insert_batch(conn, title, raw_text, user["username"])
        conn.commit()
    return batch_detail(batch_id, authorization)


if __name__ == "__main__":
    import os

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
