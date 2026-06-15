from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class ReaderMode(str, Enum):
    NEW = "new"
    FAMILIAR = "familiar"


class SummaryLength(str, Enum):
    BRIEF = "brief"
    STANDARD = "standard"
    DETAILED = "detailed"


class BookImportRequest(BaseModel):
    file_path: str
    reader_mode: ReaderMode = ReaderMode.NEW
    title: Optional[str] = None


class BookResponse(BaseModel):
    id: int
    title: str
    author: str
    content_type: str
    genre_tags: list[str] = []
    total_chars: int = 0
    chapter_count: int = 0
    created_at: str


class ChapterResponse(BaseModel):
    id: int
    book_id: int
    index_num: int
    title: str


class AtomResponse(BaseModel):
    id: int
    chapter_id: int
    reading_order: int
    content: str


class BubbleResponse(BaseModel):
    id: int
    layer: int
    title: str
    content: str  # L1→title, L2→summary, L3→detail
    importance: int
    compress_state: str
    story_time_label: Optional[str] = None
    child_count: int = 0
    has_cross_refs: bool = False
    atom_ids: list[int] = []  # L4 associated original atoms


class BubbleListResponse(BaseModel):
    bubbles: list[BubbleResponse]
    total_count: int


class BubbleChildrenResponse(BaseModel):
    """L3 expansion returns subordinate L4 sentence groups and their original atoms"""
    l4_groups: list[dict]  # [{group_description, atoms: [{id, content}]}]


class ProcessingStatus(BaseModel):
    book_id: int
    status: str  # pending / processing / complete / failed
    total_chapters: int
    processed_chapters: int
    estimated_time: Optional[str] = None


class ReadingProgressRequest(BaseModel):
    chapter_id: int
    atom_position: int
