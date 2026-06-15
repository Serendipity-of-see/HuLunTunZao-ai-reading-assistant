export interface Book {
  id: number
  title: string
  author: string
  content_type: string
  genre_tags: string[]
  total_chars: number
  chapter_count: number
  created_at: string
  processing_status?: 'pending' | 'processing' | 'complete' | 'failed'
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
  children: TreeNode[]
  jump_anchor?: JumpAnchor | null
}

export type ReaderMode = 'new' | 'familiar'
export type Layer = 1 | 2 | 3
