from fastapi import APIRouter, HTTPException
from models.schemas import BookImportRequest
from services.book_service import create_book, get_book, get_chapters, get_atoms
from services.processing import process_book_phase1
import asyncio
import os

router = APIRouter()


@router.post("/import", status_code=201)
async def import_book(req: BookImportRequest):
    """导入小说，启动 Phase 1 处理。同文件重复导入复用已有书籍记录。"""
    file_path = req.file_path.strip().strip('"').strip("'")  # 去引号
    print(f"[DEBUG] import path after strip: {repr(file_path)}")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"文件不存在: {file_path}")

    # 检查是否已导入过
    from db.connection import get_db
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM books WHERE file_path = ? ORDER BY id DESC LIMIT 1",
            (file_path,),
        )
        existing = await cursor.fetchone()
    finally:
        await db.close()

    if existing:
        book_id = existing["id"]
        reuse = True
    else:
        book = await create_book(file_path, req.reader_mode, req.title)
        book_id = book["id"]
        reuse = False

    # 异步启动 Phase 1 处理（不阻塞响应）
    asyncio.create_task(
        process_book_phase1(book_id, file_path, req.reader_mode)
    )

    return {
        "book_id": book_id,
        "status": "processing" if reuse else "processing",
        "reuse": reuse,
    }


@router.get("")
async def list_books():
    """列出所有已导入的书籍"""
    from db.connection import get_db
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT b.*,
               (SELECT COUNT(*) FROM chapters WHERE book_id = b.id) as chapter_count,
               (SELECT CASE
                   WHEN EXISTS(SELECT 1 FROM processing_state ps WHERE ps.book_id=b.id AND ps.status='failed')
                       THEN 'failed'
                   WHEN EXISTS(SELECT 1 FROM processing_state ps WHERE ps.book_id=b.id AND ps.status='processing')
                       THEN 'processing'
                   WHEN (SELECT COUNT(*) FROM processing_state ps WHERE ps.book_id=b.id AND ps.status!='complete') = 0
                        AND (SELECT COUNT(*) FROM processing_state ps WHERE ps.book_id=b.id) > 0
                       THEN 'complete'
                   ELSE 'pending'
               END) as processing_status
               FROM books b ORDER BY b.created_at DESC"""
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


@router.get("/{book_id}")
async def get_book_info(book_id: int):
    """获取书籍信息"""
    book = await get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")
    return book


@router.get("/{book_id}/chapters")
async def get_book_chapters(book_id: int):
    """获取章节目录"""
    chapters = await get_chapters(book_id)
    return {"chapters": chapters, "total": len(chapters)}


@router.get("/{book_id}/processing-status")
async def get_processing_status(book_id: int):
    """获取逐层处理进度。"""
    from db.connection import get_db
    db = await get_db()
    try:
        cursor = await db.execute(
            """SELECT ps.*, c.index_num as chapter_index, c.title as chapter_title
               FROM processing_state ps
               LEFT JOIN chapters c ON ps.chapter_id = c.id
               WHERE ps.book_id = ?
               ORDER BY ps.chapter_id, ps.step""",
            (book_id,),
        )
        rows = await cursor.fetchall()

        book_steps = {}  # {step: status}
        chapters_detail = []  # [{chapter_index, chapter_title, steps: {step: status}}]
        ch_map = {}

        for r in rows:
            rd = dict(r)
            if rd["chapter_id"] == 0:
                book_steps[rd["step"]] = {"status": rd["status"], "error": rd.get("error_message")}
            else:
                ch_idx = rd.get("chapter_index")
                if ch_idx not in ch_map:
                    ch_map[ch_idx] = {
                        "chapter_index": ch_idx,
                        "chapter_title": rd.get("chapter_title", ""),
                        "steps": {},
                    }
                ch_map[ch_idx]["steps"][rd["step"]] = {
                    "status": rd["status"],
                    "error": rd.get("error_message"),
                }

        chapters_detail = sorted(ch_map.values(), key=lambda x: x["chapter_index"])

        # 总体状态
        all_statuses = [s["status"] for s in book_steps.values()]
        for ch in chapters_detail:
            all_statuses.extend(s["status"] for s in ch["steps"].values())

        if any(s == "failed" for s in all_statuses):
            overall = "failed"
        elif all(s == "complete" for s in all_statuses) and all_statuses:
            overall = "complete"
        elif any(s == "processing" for s in all_statuses):
            overall = "processing"
        else:
            overall = "pending"

        return {
            "book_id": book_id,
            "overall_status": overall,
            "book_steps": book_steps,
            "chapters": chapters_detail,
        }
    finally:
        await db.close()


@router.post("/{book_id}/retry")
async def retry_processing(book_id: int):
    """重试失败的处理步骤。"""
    import asyncio
    from db.connection import get_db

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM processing_state WHERE book_id=? AND status='failed'",
            (book_id,),
        )
        row = await cursor.fetchone()
        if row["cnt"] == 0:
            return {"status": "ok", "message": "No failed steps to retry"}

        # 重置 failed → pending，清除错误信息
        await db.execute(
            "UPDATE processing_state SET status='pending', error_message=NULL WHERE book_id=? AND status='failed'",
            (book_id,),
        )
        await db.commit()

        # 获取书籍信息以重新处理
        cursor = await db.execute("SELECT file_path FROM books WHERE id=?", (book_id,))
        book = await cursor.fetchone()
        if not book:
            raise HTTPException(status_code=404, detail="书籍不存在")
        file_path = book["file_path"]
    finally:
        await db.close()

    asyncio.create_task(process_book_phase1(book_id, file_path, "familiar"))
    return {"status": "retrying", "book_id": book_id}


@router.get("/{book_id}/atoms")
async def get_book_atoms(
    book_id: int,
    chapter_id: int = None,
    offset: int = 0,
    limit: int = 200,
):
    """分页获取原文 atoms"""
    atoms, total = await get_atoms(book_id, chapter_id, offset, limit)
    return {"atoms": atoms, "total": total, "offset": offset, "limit": limit}
