from fastapi import APIRouter, HTTPException
from models.schemas import ReadingProgressRequest
from db.connection import get_db

router = APIRouter()


@router.get("/reading-progress/{book_id}")
async def get_reading_progress(book_id: int):
    """获取阅读进度"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM reading_progress WHERE book_id = ?", (book_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return {"book_id": book_id, "chapter_id": None, "atom_position": 0}
        return dict(row)
    finally:
        await db.close()


@router.put("/reading-progress/{book_id}")
async def update_reading_progress(book_id: int, req: ReadingProgressRequest):
    """更新阅读进度"""
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO reading_progress (book_id, chapter_id, atom_position, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(book_id) DO UPDATE SET
               chapter_id = excluded.chapter_id,
               atom_position = excluded.atom_position,
               updated_at = datetime('now')""",
            (book_id, req.chapter_id, req.atom_position),
        )
        await db.commit()
        return {"status": "ok"}
    finally:
        await db.close()
