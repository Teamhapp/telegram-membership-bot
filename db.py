import aiosqlite
from config import DB_PATH

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS users (
    user_id             INTEGER PRIMARY KEY,
    username            TEXT,
    first_name          TEXT,
    preferred_language  TEXT,
    subscription_state  TEXT DEFAULT 'NEW',
    pending_channel_id  TEXT DEFAULT '',
    conversation_summary TEXT DEFAULT '',
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER,
    channel_id      TEXT NOT NULL DEFAULT 'default',
    status          TEXT DEFAULT 'inactive',
    started_at      DATETIME,
    expires_at      DATETIME,
    reminded_3d     INTEGER DEFAULT 0,
    reminded_1d     INTEGER DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER,
    channel_id      TEXT NOT NULL DEFAULT 'default',
    amount          TEXT,
    utr             TEXT UNIQUE,
    screenshot_path TEXT,
    status          TEXT DEFAULT 'pending',
    submitted_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    reviewed_at     DATETIME,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    role        TEXT,
    content     TEXT,
    intent      TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS analytics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    event       TEXT,
    metadata    TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS faq_candidates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    question    TEXT,
    count       INTEGER DEFAULT 1,
    approved    INTEGER DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # WAL mode: better concurrent read/write performance
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.executescript(CREATE_TABLES)
        await db.commit()


async def get_user(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def upsert_user(user_id: int, username: str, first_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO users(user_id, username, first_name)
               VALUES(?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 username=excluded.username,
                 first_name=excluded.first_name""",
            (user_id, username, first_name),
        )
        await db.commit()


async def set_state(user_id: int, state: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET subscription_state=? WHERE user_id=?", (state, user_id))
        await db.commit()


async def set_language(user_id: int, language: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET preferred_language=? WHERE user_id=?", (language, user_id))
        await db.commit()


async def update_summary(user_id: int, summary: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET conversation_summary=? WHERE user_id=?", (summary, user_id))
        await db.commit()


async def get_recent_messages(user_id: int, limit: int = 10) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT role, content FROM conversations WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return list(reversed([dict(r) for r in rows]))


async def save_message(user_id: int, role: str, content: str, intent: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO conversations(user_id, role, content, intent) VALUES(?,?,?,?)",
            (user_id, role, content, intent),
        )
        await db.commit()


async def set_pending_channel(user_id: int, channel_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET pending_channel_id=? WHERE user_id=?", (channel_id, user_id))
        await db.commit()


async def get_subscription(user_id: int, channel_id: str | None = None) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if channel_id:
            q = "SELECT * FROM subscriptions WHERE user_id=? AND channel_id=? ORDER BY id DESC LIMIT 1"
            params = (user_id, channel_id)
        else:
            q = "SELECT * FROM subscriptions WHERE user_id=? ORDER BY id DESC LIMIT 1"
            params = (user_id,)
        async with db.execute(q, params) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_all_subscriptions(user_id: int) -> list[dict]:
    """Get all active subscriptions for a user across all channels."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscriptions WHERE user_id=? AND status='active' ORDER BY channel_id",
            (user_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def create_subscription(user_id: int, channel_id: str, days: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO subscriptions(user_id, channel_id, status, started_at, expires_at)
               VALUES(?, ?, 'active', CURRENT_TIMESTAMP, datetime('now', ?))""",
            (user_id, channel_id, f"+{days} days"),
        )
        await db.commit()


async def save_payment(user_id: int, channel_id: str, amount: str, utr: str, screenshot_path: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO payments(user_id, channel_id, amount, utr, screenshot_path) VALUES(?,?,?,?,?)",
            (user_id, channel_id, amount, utr, screenshot_path),
        )
        await db.commit()
        return cur.lastrowid


async def approve_payment(payment_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET status='approved', reviewed_at=CURRENT_TIMESTAMP WHERE id=?",
            (payment_id,),
        )
        await db.commit()


async def is_duplicate_utr(utr: str) -> bool:
    if not utr or utr in ("", "N/A", "unknown"):
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM payments WHERE utr=? AND status='approved'", (utr,)
        ) as cur:
            return await cur.fetchone() is not None


async def get_pending_payment(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM payments WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def track_event(user_id: int, event: str, metadata: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO analytics(user_id, event, metadata) VALUES(?,?,?)",
            (user_id, event, metadata),
        )
        await db.commit()


async def upsert_faq_candidate(question: str):
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await db.execute(
            "SELECT id, count FROM faq_candidates WHERE question=? AND approved=0", (question,)
        )
        row = await existing.fetchone()
        if row:
            await db.execute("UPDATE faq_candidates SET count=? WHERE id=?", (row[1] + 1, row[0]))
        else:
            await db.execute("INSERT INTO faq_candidates(question) VALUES(?)", (question,))
        await db.commit()


async def get_faq_candidates(min_count: int = 3) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM faq_candidates WHERE approved=0 AND count>=? ORDER BY count DESC",
            (min_count,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def prune_history(user_id: int, keep: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """DELETE FROM conversations WHERE user_id=? AND id NOT IN (
               SELECT id FROM conversations WHERE user_id=?
               ORDER BY id DESC LIMIT ?)""",
            (user_id, user_id, keep),
        )
        await db.commit()


async def get_analytics_events() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT event, COUNT(*) as count FROM analytics GROUP BY event ORDER BY count DESC"
        ) as cur:
            return {r["event"]: r["count"] for r in await cur.fetchall()}


async def get_active_subscription_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE status='active'"
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_total_user_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def approve_faq_candidate(candidate_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE faq_candidates SET approved=1 WHERE id=?", (candidate_id,))
        await db.commit()
