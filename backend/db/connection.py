import aiosqlite
from config import DB_PATH


async def get_db():
    """Get a database connection. The caller is responsible for closing it."""
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    """Initialize database tables. Call once at application startup."""
    db = await get_db()
    try:
        await db.executescript(SCHEMA_SQL)
        await db.commit()
    finally:
        await db.close()


from db.schema import SCHEMA_SQL  # noqa: E402 — placed at bottom to avoid circular import
