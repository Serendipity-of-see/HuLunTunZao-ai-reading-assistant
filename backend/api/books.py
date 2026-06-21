from fastapi import APIRouter, HTTPException, UploadFile, Request
from fastapi.responses import StreamingResponse
from models.schemas import BookImportRequest
from services.book_service import create_book, get_book, get_chapters, get_atoms
from services.processing import process_book_phase1
from services.progress_tracker import tracker
import asyncio
import json
import os

router = APIRouter()

# ── 活跃任务注册表（用于取消）────────────────────────────────
_active_tasks: dict[int, asyncio.Task] = {}


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
    task = asyncio.create_task(
        process_book_phase1(book_id, file_path, req.reader_mode)
    )
    def _on_done(t):
        _active_tasks.pop(book_id, None)
        try:
            if exc := t.exception():
                if not isinstance(exc, asyncio.CancelledError):
                    print(f"[ERROR] Book {book_id} processing task failed: {exc}")
        except Exception:
            pass  # 忽略取异常时的错误
    task.add_done_callback(_on_done)
    _active_tasks[book_id] = task

    return {
        "book_id": book_id,
        "status": "processing",
        "reuse": reuse,
    }


@router.post("/import-file", status_code=201)
async def import_book_file(file: UploadFile):
    """通过文件上传导入小说，启动 Phase 1 处理。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名为空")

    # 保存到临时目录
    import tempfile
    suffix = os.path.splitext(file.filename)[1] or '.txt'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        file_path = tmp.name

    # 创建书籍记录
    title = os.path.splitext(file.filename)[0]
    book = await create_book(file_path, "familiar", title)
    book_id = book["id"]

    task = asyncio.create_task(process_book_phase1(book_id, file_path, "familiar"))
    def _on_done(t):
        _active_tasks.pop(book_id, None)
        try: os.unlink(file_path)
        except OSError: pass
        if exc := t.exception():
            if not isinstance(exc, asyncio.CancelledError):
                print(f"[ERROR] Book {book_id} failed: {exc}")
    task.add_done_callback(_on_done)
    _active_tasks[book_id] = task

    return {"book_id": book_id, "status": "processing", "reuse": False}


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
        books = []
        for row in rows:
            d = dict(row)
            if d.get("genre_tags") and isinstance(d["genre_tags"], str):
                try: d["genre_tags"] = json.loads(d["genre_tags"])
                except json.JSONDecodeError: d["genre_tags"] = []
            books.append(d)
        return books
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

        # 合并 ProgressTracker 快照（SSE 进度详情）
        snapshot = tracker.get_snapshot(book_id)
        return {
            "book_id": book_id,
            "overall_status": overall,
            "book_steps": book_steps,
            "chapters": chapters_detail,
            # 以下为实时进度字段（来自 ProgressTracker）
            "current_step": snapshot.get("current_step"),
            "step_label": snapshot.get("step_label"),
            "step_progress_current": snapshot.get("step_progress_current"),
            "step_progress_total": snapshot.get("step_progress_total"),
            "progress_pct": snapshot.get("progress_pct", 0),
            "recent_details": snapshot.get("recent_details", []),
            "total_chapters": snapshot.get("total_chapters"),
            "steps_completed": snapshot.get("steps_completed", []),
            "steps_failed": snapshot.get("steps_failed", []),
        }
    finally:
        await db.close()


@router.get("/{book_id}/progress-stream")
async def progress_stream(book_id: int, request: Request):
    """SSE 端点：实时推送处理进度事件流。

    客户端连接后先收到当前快照（snapshot），再收到实时事件。
    检测客户端断开后自动释放连接。
    """
    async def event_generator():
        try:
            async for event_json in tracker.subscribe(book_id):
                if await request.is_disconnected():
                    break
                yield f"data: {event_json}\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{book_id}/retry")
async def retry_processing(book_id: int):
    """重试失败的处理步骤。"""
    import asyncio
    from db.connection import get_db

    if book_id in _active_tasks and not _active_tasks[book_id].done():
        return {"status": "ok", "message": "已有处理任务在进行中"}

    db = await get_db()
    try:
        # 检查是否有需要处理的步骤（failed 或 pending）
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM processing_state WHERE book_id=? AND status IN ('failed','pending')",
            (book_id,),
        )
        row = await cursor.fetchone()
        if row["cnt"] == 0:
            return {"status": "ok", "message": "所有步骤已完成，无需重试"}

        # 重置 failed/pending → pending，清除错误信息
        await db.execute(
            "UPDATE processing_state SET status='pending', error_message=NULL WHERE book_id=? AND status IN ('failed','pending')",
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

    task = asyncio.create_task(process_book_phase1(book_id, file_path, "familiar"))
    def _on_done(t):
        _active_tasks.pop(book_id, None)
        if exc := t.exception():
            if not isinstance(exc, asyncio.CancelledError):
                print(f"[ERROR] Book {book_id} retry failed: {exc}")
    task.add_done_callback(_on_done)
    _active_tasks[book_id] = task
    return {"status": "retrying", "book_id": book_id}


@router.post("/{book_id}/cancel")
async def cancel_processing(book_id: int):
    """取消正在进行的处理任务，保留已完成数据可断点续处理。"""
    task = _active_tasks.pop(book_id, None)
    if task and not task.done():
        task.cancel()
    # 重置所有 processing 状态为 pending（适应重启后任务丢失的情况）
    from db.connection import get_db
    db = await get_db()
    try:
        await db.execute(
            "UPDATE processing_state SET status='pending', error_message=NULL WHERE book_id=? AND status='processing'",
            (book_id,)
        )
        await db.commit()
    finally:
        await db.close()
    if task:
        return {"status": "cancelled", "book_id": book_id}
    return {"status": "reset", "book_id": book_id, "message": "未找到活跃任务，已重置处理状态"}


@router.delete("/{book_id}")
async def delete_book_endpoint(book_id: int):
    """删除书籍及其所有关联数据。先取消正在进行的处理。"""
    from db.connection import get_db
    book = await get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")

    # 取消正在进行的处理任务
    task = _active_tasks.pop(book_id, None)
    if task and not task.done():
        task.cancel()

    db = await get_db()
    try:
        await db.execute("DELETE FROM processing_state WHERE book_id = ?", (book_id,))
        await db.execute("DELETE FROM atoms WHERE book_id = ?", (book_id,))
        await db.execute("DELETE FROM plot_nodes WHERE book_id = ?", (book_id,))
        await db.execute("DELETE FROM chapters WHERE book_id = ?", (book_id,))
        await db.execute("DELETE FROM reading_progress WHERE book_id = ?", (book_id,))
        await db.execute("DELETE FROM books WHERE id = ?", (book_id,))
        await db.commit()
    finally:
        await db.close()
    return {"status": "deleted", "book_id": book_id}


@router.get("/{book_id}/export")
async def export_book_endpoint(book_id: int):
    """导出书籍的完整解析结果为 .hltz JSON。"""
    from services.export_service import export_book as do_export

    book = await get_book(book_id)
    if not book:
        raise HTTPException(status_code=404, detail="书籍不存在")

    data = await do_export(book_id)
    return data


@router.post("/import-hltz", status_code=201)
async def import_hltz_endpoint(file: UploadFile):
    """从 .hltz 文件导入已解析的书籍。"""
    from services.import_service import import_hltz

    if not file.filename or not file.filename.endswith(".hltz"):
        raise HTTPException(status_code=400, detail="请上传 .hltz 文件")

    try:
        raw = await file.read()
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="无法解析 .hltz 文件，请确认文件格式正确")

    try:
        book_id = await import_hltz(data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"book_id": book_id, "status": "imported"}


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
