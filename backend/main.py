from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db.connection import init_db
from services.processing import migrate_processing_state
from api.books import router as books_router
from api.bubbles import router as bubbles_router
from api.reading import router as reading_router
from api.settings import router as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化数据库
    await init_db()
    await migrate_processing_state()
    # 清理上次异常退出遗留的 processing 状态
    await _reset_stuck_processing()
    yield


async def _reset_stuck_processing():
    """将上次会话遗留的 processing 状态重置为 pending。"""
    from db.connection import get_db
    db = await get_db()
    try:
        cursor = await db.execute(
            "UPDATE processing_state SET status='pending', error_message='Server restarted during processing' "
            "WHERE status='processing'"
        )
        if cursor.rowcount > 0:
            print(f"[STARTUP] Reset {cursor.rowcount} stuck 'processing' states to 'pending'")
            await db.commit()
    finally:
        await db.close()


app = FastAPI(
    title="囫囵吞枣 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8765",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8765",
        "tauri://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books_router, prefix="/api/books", tags=["books"])
app.include_router(bubbles_router, prefix="/api/books", tags=["bubbles"])
app.include_router(reading_router, prefix="/api", tags=["reading"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
