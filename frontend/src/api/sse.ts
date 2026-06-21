/**
 * SSE 进度流客户端 — EventSource 封装。
 *
 * 特性：
 * - 自动重连（指数退避，最多 5 次）
 * - 降级到轮询（SSE 彻底失败时）
 * - AbortSignal 清理
 */

import type { ProgressEvent } from '../types'
import { api } from './client'

const API_HOST = import.meta.env.DEV ? '' : 'http://localhost:8765'
const MAX_RETRIES = 5
const POLL_INTERVAL = 2000 // 降级轮询间隔（ms）

interface StreamCallbacks {
  onEvent: (event: ProgressEvent) => void
  onDisconnect: () => void
}

export function createProgressStream(
  bookId: number,
  callbacks: StreamCallbacks,
  signal: AbortSignal,
): { close: () => void } {
  let es: EventSource | null = null
  let retryCount = 0
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let closed = false

  const { onEvent, onDisconnect } = callbacks

  // ── 降级轮询 ──────────────────────────────────────────────
  const startPolling = () => {
    if (pollTimer || closed) return
    pollTimer = setInterval(async () => {
      if (closed) { stopPolling(); return }
      try {
        const status = await api.getProcessingStatus(bookId)
        if (status.overall_status === 'complete' || status.overall_status === 'failed') {
          stopPolling()
        }
        onEvent({
          type: 'snapshot',
          overall_status: status.overall_status,
          current_step: status.current_step,
          step_label: status.step_label,
          step_progress_current: status.step_progress_current ?? undefined,
          step_progress_total: status.step_progress_total ?? undefined,
          progress_pct: status.progress_pct,
          recent_details: status.recent_details,
          total_chapters: status.total_chapters,
          steps_completed: status.steps_completed || [],
          steps_failed: status.steps_failed || [],
        })
      } catch { /* retry next tick */ }
    }, POLL_INTERVAL)
  }

  const stopPolling = () => {
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  }

  // ── SSE 连接 ──────────────────────────────────────────────
  const connect = () => {
    if (closed) return
    stopPolling() // 停止降级轮询

    const url = `${API_HOST}/api/books/${bookId}/progress-stream`
    es = new EventSource(url)

    es.onmessage = (msg) => {
      retryCount = 0 // 收到消息则重置重试计数
      try {
        const data = JSON.parse(msg.data) as ProgressEvent
        onEvent(data)
        if (data.type === 'complete' || data.type === 'error') {
          close()
        }
      } catch { /* 忽略解析错误 */ }
    }

    es.onerror = () => {
      if (closed) return
      es?.close()
      es = null

      retryCount++
      if (retryCount >= MAX_RETRIES) {
        // 降级到轮询
        onDisconnect()
        startPolling()
        return
      }

      // 指数退避重连
      const delay = Math.min(1000 * Math.pow(2, retryCount - 1), 16000)
      retryTimer = setTimeout(connect, delay)
    }

    es.onopen = () => {
      retryCount = 0
    }
  }

  const close = () => {
    closed = true
    es?.close()
    es = null
    if (retryTimer) { clearTimeout(retryTimer); retryTimer = null }
    stopPolling()
  }

  // 监听外部取消信号
  signal.addEventListener('abort', close, { once: true })

  // 开始连接
  connect()

  return { close }
}
