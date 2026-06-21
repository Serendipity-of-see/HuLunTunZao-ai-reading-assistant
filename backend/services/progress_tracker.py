"""处理进度追踪器 — 模块级单例，管理每本书的事件队列和状态快照。

管线通过 push() 推送事件；SSE 端点通过 subscribe() 订阅事件流；
轮询端点通过 get_snapshot() 获取累积状态。
"""

import asyncio
import json
import time
from typing import Optional

# ── 步骤权重（用于进度百分比计算）──────────────────────────────
STEP_WEIGHTS = {
    "parse": 5,
    "l4": 10,
    "l3": 70,
    "l2_global": 7,
    "l1_merge": 5,
    "done": 3,
}

STEP_LABELS = {
    "parse": "章节解析",
    "l4": "语义分组",
    "l3": "场景聚合",
    "l2_global": "跨章聚合",
    "l1_merge": "宏观叙事",
    "done": "完成",
}

# 所有步骤按顺序
ALL_STEPS = ["parse", "l4", "l3", "l2_global", "l1_merge", "done"]


class ProgressTracker:
    """处理进度追踪器（单例）。"""

    _instance: Optional["ProgressTracker"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._queues: dict[int, asyncio.Queue] = {}
            cls._instance._snapshots: dict[int, dict] = {}
            cls._instance._finished_at: dict[int, float] = {}
            cls._instance._cleanup_task = None
        return cls._instance

    # ── 公共 API ──────────────────────────────────────────────

    def push(self, book_id: int, event: dict):
        """管线调用：推送一个进度事件。"""
        q = self._ensure_queue(book_id)
        try:
            q.put_nowait(json.dumps(event, ensure_ascii=False))
        except asyncio.QueueFull:
            # 队列满时丢弃最旧事件（防止内存泄漏）
            try:
                q.get_nowait()
                q.put_nowait(json.dumps(event, ensure_ascii=False))
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass

        # 更新快照
        self._update_snapshot(book_id, event)

    async def subscribe(self, book_id: int):
        """SSE 订阅：先 yield 快照，再 yield 实时事件，直到终端状态或客户端断开。

        客户端断开时 asyncio.CancelledError 向上传播，由调用方处理。
        """
        # 先发送快照
        snapshot = self.get_snapshot(book_id)
        yield json.dumps({"type": "snapshot", **snapshot}, ensure_ascii=False)

        q = self._ensure_queue(book_id)
        while True:
            try:
                event_json = await asyncio.wait_for(q.get(), timeout=30)
                yield event_json
                data = json.loads(event_json)
                if data.get("type") in ("complete", "error"):
                    break
            except asyncio.TimeoutError:
                # 30 秒无事件，检查是否已结束
                snapshot = self._snapshots.get(book_id, {})
                if snapshot.get("overall_status") in ("complete", "failed"):
                    break
                # 未结束则继续等待

    def get_snapshot(self, book_id: int) -> dict:
        """返回某本书的当前进度快照（轮询用）。"""
        return self._snapshots.get(book_id, self._empty_snapshot(book_id))

    # ── 内部 ──────────────────────────────────────────────────

    def _ensure_queue(self, book_id: int) -> asyncio.Queue:
        if book_id not in self._queues:
            self._queues[book_id] = asyncio.Queue(maxsize=500)
            self._snapshots[book_id] = self._empty_snapshot(book_id)
        return self._queues[book_id]

    @staticmethod
    def _empty_snapshot(book_id: int) -> dict:
        return {
            "book_id": book_id,
            "overall_status": "pending",
            "current_step": None,
            "step_label": None,
            "step_progress_current": None,
            "step_progress_total": None,
            "progress_pct": 0.0,
            "chapter_index": None,
            "chapter_title": None,
            "recent_details": [],
            "total_chapters": None,
            "steps_completed": [],
            "steps_failed": [],
        }

    def _update_snapshot(self, book_id: int, event: dict):
        snap = self._snapshots.get(book_id)
        if snap is None:
            snap = self._empty_snapshot(book_id)
            self._snapshots[book_id] = snap

        etype = event.get("type", "")

        if etype == "context":
            if "total_chapters" in event:
                snap["total_chapters"] = event["total_chapters"]

        elif etype == "step_start":
            snap["overall_status"] = "processing"
            snap["current_step"] = event.get("step")
            snap["step_label"] = event.get("label") or STEP_LABELS.get(event.get("step", ""), "")
            snap["step_progress_current"] = 0
            snap["step_progress_total"] = event.get("total_groups") or event.get("total")
            if "chapter_index" in event:
                snap["chapter_index"] = event["chapter_index"]
            if "chapter_title" in event:
                snap["chapter_title"] = event["chapter_title"]

        elif etype == "progress":
            snap["current_step"] = event.get("step")
            snap["step_progress_current"] = event.get("current")
            snap["step_progress_total"] = event.get("total")
            pct = self._calc_progress(book_id)
            snap["progress_pct"] = pct

        elif etype == "l3_progress":
            snap["current_step"] = event.get("step")
            snap["step_progress_current"] = event.get("current")
            snap["step_progress_total"] = event.get("total")

            scene_title = event.get("scene_title", "")
            is_new = event.get("is_new", False)
            if scene_title:
                snap["recent_details"].append({"title": scene_title, "is_new": is_new})
                # 只保留最近 20 条
                if len(snap["recent_details"]) > 20:
                    snap["recent_details"] = snap["recent_details"][-20:]

            # 计算 L3 进度百分比
            pct = self._calc_progress(book_id)
            snap["progress_pct"] = pct

        elif etype == "step_complete":
            step = event.get("step", "")
            if step and step not in snap["steps_completed"]:
                snap["steps_completed"].append(step)
            snap["current_step"] = step
            pct = self._calc_progress(book_id)
            snap["progress_pct"] = pct

        elif etype == "complete":
            snap["overall_status"] = "complete"
            snap["progress_pct"] = 100.0
            snap["current_step"] = "done"
            snap["step_label"] = "完成"
            self._finished_at[book_id] = time.time()
            self._schedule_cleanup()

        elif etype == "error":
            snap["overall_status"] = "failed"
            failed_step = event.get("step", "")
            if failed_step and failed_step not in snap["steps_failed"]:
                snap["steps_failed"].append(failed_step)
            self._finished_at[book_id] = time.time()
            self._schedule_cleanup()

    def _calc_progress(self, book_id: int) -> float:
        """基于已完成步骤 + 当前步骤进度计算总体百分比。"""
        snap = self._snapshots.get(book_id)
        if not snap:
            return 0.0

        pct = 0.0
        for step in ALL_STEPS:
            weight = STEP_WEIGHTS.get(step, 0)
            if step in snap["steps_completed"]:
                pct += weight
            elif step == snap.get("current_step"):
                current = snap.get("step_progress_current") or 0
                total = snap.get("step_progress_total") or 1
                if total > 0:
                    pct += weight * (current / total)
                break
            else:
                break
        return min(round(pct, 1), 99.9)

    def _schedule_cleanup(self):
        """延迟清理已完成的队列（10 分钟后）。"""
        if self._cleanup_task is None or self._cleanup_task.done():

            async def _cleanup_later():
                await asyncio.sleep(600)  # 10 分钟
                now = time.time()
                to_remove = [
                    bid
                    for bid, ft in self._finished_at.items()
                    if now - ft > 580  # 给 20 秒缓冲
                ]
                for bid in to_remove:
                    self._queues.pop(bid, None)
                    self._snapshots.pop(bid, None)
                    self._finished_at.pop(bid, None)

            try:
                loop = asyncio.get_event_loop()
                self._cleanup_task = loop.create_task(_cleanup_later())
            except RuntimeError:
                pass


# 模块级单例
tracker = ProgressTracker()
