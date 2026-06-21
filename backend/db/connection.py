import aiosqlite
from config import DB_PATH


async def get_db():
    """Get a database connection. The caller is responsible for closing it.
    启用 WAL 模式 + 忙等待超时，避免 "database is locked" 错误。"""
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=30000")
    return db


async def init_db():
    """Initialize database tables + migrate old schemas. Call once at startup."""
    db = await get_db()
    try:
        await db.executescript(SCHEMA_SQL)
        # 迁移：给旧库添加处理统计列
        migrations = [
            "ALTER TABLE books ADD COLUMN processing_time REAL DEFAULT 0",
            "ALTER TABLE books ADD COLUMN tokens_in INTEGER DEFAULT 0",
            "ALTER TABLE books ADD COLUMN tokens_out INTEGER DEFAULT 0",
            "ALTER TABLE books ADD COLUMN model_used TEXT DEFAULT ''",
        ]
        for sql in migrations:
            try:
                await db.execute(sql)
            except Exception:
                pass  # 列已存在
        await db.commit()
    finally:
        await db.close()


from db.schema import SCHEMA_SQL  # noqa: E402 — placed at bottom to avoid circular import
