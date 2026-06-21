import json
import aiosqlite
from db.connection import get_db


async def create_book(file_path: str, reader_mode: str, title: str = None) -> dict:
    """创建书籍记录。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT INTO books (title, file_path, format, content_type) VALUES (?, ?, 'txt', 'fiction')",
            (title or "未命名", file_path),
        )
        await db.commit()
        book_id = cursor.lastrowid

        # 初始化阅读进度
        await db.execute(
            "INSERT INTO reading_progress (book_id, atom_position) VALUES (?, 0)",
            (book_id,),
        )
        await db.commit()

        return {"id": book_id, "title": title or "未命名", "status": "created"}
    finally:
        await db.close()


async def get_book(book_id: int) -> dict | None:
    """获取书籍详情（含处理状态）。"""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        row_dict = dict(row)

        # 获取章数
        cursor2 = await db.execute(
            "SELECT COUNT(*) as cnt FROM chapters WHERE book_id = ?", (book_id,)
        )
        count_row = await cursor2.fetchone()
        row_dict["chapter_count"] = count_row["cnt"] if count_row else 0

        # 计算 processing_status
        cursor3 = await db.execute(
            """SELECT CASE
                WHEN EXISTS(SELECT 1 FROM processing_state WHERE book_id=? AND status='failed')
                    THEN 'failed'
                WHEN EXISTS(SELECT 1 FROM processing_state WHERE book_id=? AND status='processing')
                    THEN 'processing'
                WHEN (SELECT COUNT(*) FROM processing_state WHERE book_id=? AND status!='complete') = 0
                     AND (SELECT COUNT(*) FROM processing_state WHERE book_id=?) > 0
                    THEN 'complete'
                ELSE 'pending'
            END as status""",
            (book_id, book_id, book_id, book_id),
        )
        status_row = await cursor3.fetchone()
        row_dict["processing_status"] = status_row["status"] if status_row else "pending"

        # 解析 JSON 字段
        if row_dict.get("genre_tags"):
            row_dict["genre_tags"] = json.loads(row_dict["genre_tags"])

        return row_dict
    finally:
        await db.close()


async def get_chapters(book_id: int) -> list[dict]:
    """获取章节目录。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM chapters WHERE book_id = ? ORDER BY index_num",
            (book_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_atoms(
    book_id: int,
    chapter_id: int | None = None,
    offset: int = 0,
    limit: int = 200,
) -> tuple[list[dict], int]:
    """分页获取 atoms。"""
    db = await get_db()
    try:
        base_count = "SELECT COUNT(*) as cnt FROM atoms"
        base_query = "SELECT * FROM atoms"
        if chapter_id:
            count_sql = f"{base_count} WHERE book_id = ? AND chapter_id = ?"
            query_sql = f"{base_query} WHERE book_id = ? AND chapter_id = ? ORDER BY reading_order LIMIT ? OFFSET ?"
            params_count = (book_id, chapter_id)
            params_query = (book_id, chapter_id, limit, offset)
        else:
            count_sql = f"{base_count} WHERE book_id = ?"
            query_sql = f"{base_query} WHERE book_id = ? ORDER BY reading_order LIMIT ? OFFSET ?"
            params_count = (book_id,)
            params_query = (book_id, limit, offset)

        cursor = await db.execute(count_sql, params_count)
        total = (await cursor.fetchone())["cnt"]

        cursor = await db.execute(query_sql, params_query)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows], total
    finally:
        await db.close()
