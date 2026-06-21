export interface CrossRef {
  target_id?: number
  target_index?: number
  relation_type: string
  description: string
}

export interface Book {
  id: number
  title: string
  author: string
  content_type: string
  genre_tags: string[]
  total_chars: number
  chapter_count: number
  narrative_summary?: string
  created_at: string
  processing_status?: 'pending' | 'processing' | 'complete' | 'failed'
  processing_time?: number
  tokens_in?: number
  tokens_out?: number
  model_used?: string
}

export interface ChapterStep {
  step: string
  status: string
  error: string | null
}

export interface ChapterProgress {
  chapter_index: number
  chapter_title: string
  steps: Record<string, ChapterStep>
}

export interface ProcessingStatus {
  book_id: number
  overall_status: string
  book_steps: Record<string, ChapterStep>
  chapters: ChapterProgress[]
  // 实时进度字段（来自 ProgressTracker）
  current_step?: string | null
  step_label?: string | null
  step_progress_current?: number | null
  step_progress_total?: number | null
  progress_pct?: number
  recent_details?: { title: string; is_new: boolean }[]
  total_chapters?: number | null
  steps_completed?: string[]
  steps_failed?: string[]
}

// ── 增量树更新事件 ──────────────────────────────────────────

export interface NodeAddEvent {
  type: 'node_add'
  parent_id: number
  node: TreeNode
}

export interface NodeDeleteEvent {
  type: 'node_delete'
  node_id: number
}

// ── SSE 进度事件类型 ────────────────────────────────────────

export interface ProgressEvent {
  type: 'step_start' | 'l3_progress' | 'progress' | 'step_complete' | 'complete' | 'error' | 'snapshot' | 'context' | 'tokens' | 'stream' | 'reasoning' | 'stats' | 'tree_refresh' | 'node_add' | 'node_delete'
  step?: string
  label?: string
  current_step?: string | null
  step_label?: string | null
  current?: number
  total?: number
  scene_title?: string
  is_new?: boolean
  groups_count?: number
  scenes_count?: number
  groups?: number
  chapter_index?: number
  chapter_title?: string
  chapters_count?: number
  total_groups?: number
  total_groups_done?: number
  total_chapters?: number | null
  book_title?: string
  message?: string
  progress_pct?: number
  // snapshot 中包含的字段
  overall_status?: string
  step_progress_current?: number | null
  step_progress_total?: number | null
  recent_details?: { title: string; is_new: boolean }[]
  steps_completed?: string[]
  steps_failed?: string[]
  tokens_in?: number
  tokens_out?: number
  text?: string
  total_elapsed?: number
  total_tokens_in?: number
  total_tokens_out?: number
  // node_add / node_delete
  parent_id?: number
  node?: TreeNode
  node_id?: number
}

export interface ProgressSnapshot {
  book_id: number
  overall_status: 'pending' | 'processing' | 'complete' | 'failed'
  current_step: string | null
  step_label: string | null
  step_progress_current: number | null
  step_progress_total: number | null
  progress_pct: number
  chapter_index: number | null
  chapter_title: string | null
  recent_details: { title: string; is_new: boolean }[]
  total_chapters: number | null
  steps_completed: string[]
  steps_failed: string[]
}

export interface Chapter {
  id: number
  book_id: number
  index_num: number
  title: string
}

export interface Atom {
  id: number
  chapter_id: number
  reading_order: number
  content: string
}

export interface Bubble {
  id: number
  layer: number
  title: string
  content: string
  importance: number
  compress_state: string
  story_time_label: string | null
  child_count: number
  has_cross_refs: boolean
}

export interface L4Group {
  group_id: number
  summary: string
  atoms: { id: number; content: string }[]
}

export interface BubbleChildren {
  l4_groups?: L4Group[]
  children?: Bubble[]
}

export interface JumpAnchor {
  chapter_index: number
  atom_id: number
  reading_order: number
}

export interface TreeNode {
  id: number
  layer: number
  title: string
  content: string
  importance: number
  story_time_label: string | null
  child_count: number
  has_cross_refs: boolean
  cross_refs: CrossRef[]
  children: TreeNode[]
  jump_anchor?: JumpAnchor | null
}

export interface HltzExport {
  hltz_version: number
  exported_at: string
  book: { title: string; author: string; total_chars: number }
  run: { label: string; profile: string; model_used: string; created_at: string; completed_at: string }
  data: { narrative_summary: string; genre_tags: string[]; chapters: unknown[]; plot_nodes: unknown[] }
}

export type ReaderMode = 'new' | 'familiar'
export type Layer = 1 | 2 | 3
