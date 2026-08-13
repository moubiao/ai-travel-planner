"""SQLite 数据层：用户账户 + 旅行方案历史记录

- 密码存储：PBKDF2-HMAC-SHA256 加盐哈希（标准库实现，不依赖第三方）
- 认证令牌：JWT（PyJWT），7 天有效期
"""
import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"
JWT_SECRET = "travel-planner-dev-secret-change-in-prod"  # 演示项目密钥
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 7


# ---------- 基础连接 ----------
def get_conn() -> sqlite3.Connection:
    """获取数据库连接（Row 工厂）"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """初始化数据表（应用启动时调用）"""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                requirement TEXT,
                plan TEXT NOT NULL,
                `references` TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)


# ---------- 密码哈希 ----------
def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """PBKDF2 加盐哈希，返回 (哈希值, 盐)"""
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations=100_000
    )
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """校验密码"""
    digest, _ = _hash_password(password, salt)
    return secrets.compare_digest(digest, password_hash)


# ---------- JWT ----------
def create_token(user_id: int, username: str) -> str:
    """生成 JWT 令牌（7 天有效期）"""
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解析 JWT，失败抛出 jwt.PyJWTError"""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


# ---------- 用户操作 ----------
def create_user(username: str, password: str) -> dict:
    """创建用户，返回用户信息（用户名重复时抛 ValueError）"""
    password_hash, salt = _hash_password(password)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
                (username, password_hash, salt, created_at),
            )
            return {"id": cur.lastrowid, "username": username}
        except sqlite3.IntegrityError:
            raise ValueError("用户名已存在")


def get_user_by_username(username: str) -> sqlite3.Row | None:
    """按用户名查询用户"""
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    """按 ID 查询用户"""
    with get_conn() as conn:
        return conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()


# ---------- 历史方案操作 ----------
def save_plan(user_id: int, title: str, requirement: dict | None,
              plan: dict, references: list | None) -> int:
    """保存旅行方案，返回方案 ID"""
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO plans (user_id, title, requirement, plan, `references`, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                user_id, title,
                json.dumps(requirement, ensure_ascii=False) if requirement else None,
                json.dumps(plan, ensure_ascii=False),
                json.dumps(references, ensure_ascii=False) if references else None,
                created_at,
            ),
        )
        return cur.lastrowid


def list_plans(user_id: int) -> list[dict]:
    """查询用户的历史方案列表（不含完整方案，按时间倒序）"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, requirement, created_at FROM plans"
            " WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_plan(plan_id: int, user_id: int) -> dict | None:
    """查询方案详情（校验归属）"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM plans WHERE id = ? AND user_id = ?", (plan_id, user_id)
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    result["requirement"] = json.loads(result["requirement"]) if result["requirement"] else None
    result["plan"] = json.loads(result["plan"])
    result["references"] = json.loads(result["references"]) if result["references"] else []
    return result


def delete_plan(plan_id: int, user_id: int) -> bool:
    """删除方案（校验归属），返回是否删除成功"""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM plans WHERE id = ? AND user_id = ?", (plan_id, user_id))
        return cur.rowcount > 0
