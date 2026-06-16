import type { Book, Chapter, Atom, Bubble, BubbleChildren, TreeNode, ProcessingStatus, ReaderMode } from '../types'

// Vite dev: uses proxy from vite.config.ts. Production: direct to localhost.
const API_HOST = import.meta.env.DEV ? '' : 'http://localhost:8765'
const BASE = `${API_HOST}/api`

async function fetchJSON<T>(url: string, options?: RequestInit, timeoutMs = 30000): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${BASE}${url}`, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      ...options,
    })
    if (!res.ok) {
      const err = await res.text()
      throw new Error(`API ${res.status}: ${err}`)
    }
    return res.json()
  } finally {
    clearTimeout(timer)
  }
}

export const api = {
  // 书籍
  importBook: (filePath: string, readerMode: ReaderMode) =>
    fetchJSON<{ book_id: number; status: string }>('/books/import', {
      method: 'POST',
      body: JSON.stringify({ file_path: filePath, reader_mode: readerMode }),
    }),

  listBooks: () =>
    fetchJSON<Book[]>('/books'),

  getBook: (id: number) =>
    fetchJSON<Book>(`/books/${id}`),

  getChapters: (bookId: number) =>
    fetchJSON<{ chapters: Chapter[]; total: number }>(`/books/${bookId}/chapters`),

  getAtoms: (bookId: number, chapterId?: number, offset = 0, limit = 200) =>
    fetchJSON<{ atoms: Atom[]; total: number }>(
      `/books/${bookId}/atoms?chapter_id=${chapterId ?? ''}&offset=${offset}&limit=${limit}`
    ),

  // 气泡
  getTree: (bookId: number) =>
    fetchJSON<{ tree: TreeNode[]; total: number }>(`/books/${bookId}/tree`),

  getBubbles: (bookId: number, layer: number) =>
    fetchJSON<{ bubbles: Bubble[]; total_count: number }>(
      `/books/${bookId}/bubbles?layer=${layer}`
    ),

  getBubbleChildren: (bookId: number, nodeId: number) =>
    fetchJSON<BubbleChildren>(`/books/${bookId}/bubble/${nodeId}/children`),

  // 阅读进度
  getProgress: (bookId: number) =>
    fetchJSON<{ book_id: number; chapter_id: number | null; atom_position: number }>(
      `/reading-progress/${bookId}`
    ),

  updateProgress: (bookId: number, chapterId: number, atomPosition: number) =>
    fetchJSON<{ status: string }>(`/reading-progress/${bookId}`, {
      method: 'PUT',
      body: JSON.stringify({ chapter_id: chapterId, atom_position: atomPosition }),
    }),

  // 处理进度
  getProcessingStatus: (bookId: number) =>
    fetchJSON<ProcessingStatus>(`/books/${bookId}/processing-status`),

  retryProcessing: (bookId: number) =>
    fetchJSON<{ status: string }>(`/books/${bookId}/retry`, { method: 'POST' }),

  // 设置
  getSettings: () =>
    fetchJSON<{ api_key_configured: boolean; api_key_masked: string; api_base_url: string }>('/settings'),

  updateSettings: (apiKey: string) =>
    fetchJSON<{ status: string }>('/settings', {
      method: 'PUT',
      body: JSON.stringify({ api_key: apiKey }),
    }),

  validateApiKey: () =>
    fetchJSON<{ valid: boolean; message: string }>('/settings/validate', { method: 'POST' }),
}
