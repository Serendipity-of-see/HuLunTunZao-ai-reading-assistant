SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT '未命名',
    author TEXT DEFAULT '',
    file_path TEXT,
    format TEXT DEFAULT 'txt',
    content_type TEXT DEFAULT 'fiction',
    genre_tags TEXT DEFAULT '[]',       -- JSON array
    narrative_summary TEXT,
    total_chars INTEGER DEFAULT 0,
    processing_time REAL DEFAULT 0,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    model_used TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id),
    index_num INTEGER NOT NULL,
    title TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS atoms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL REFERENCES chapters(id),
    book_id INTEGER NOT NULL REFERENCES books(id),
    paragraph_id INTEGER DEFAULT 0,
    reading_order INTEGER NOT NULL,
    content TEXT NOT NULL,
    plot_node_id INTEGER REFERENCES plot_nodes(id)
);

CREATE TABLE IF NOT EXISTS plot_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id),
    parent_id INTEGER REFERENCES plot_nodes(id),
    layer INTEGER NOT NULL CHECK(layer BETWEEN 0 AND 4),
    node_type TEXT DEFAULT 'plot',
    title TEXT,
    summary TEXT,
    detail TEXT,
    importance INTEGER DEFAULT 5 CHECK(importance BETWEEN 1 AND 10),
    compress_state TEXT DEFAULT 'detail',
    st_label TEXT,
    st_sort_key REAL,
    st_ref_plot_node_id INTEGER REFERENCES plot_nodes(id),
    cross_refs TEXT DEFAULT '[]'  -- JSON: [{target_id, relation_type, description}]
);

CREATE TABLE IF NOT EXISTS reading_progress (
    book_id INTEGER PRIMARY KEY REFERENCES books(id),
    chapter_id INTEGER,
    atom_position INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS processing_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL REFERENCES books(id),
    chapter_id INTEGER NOT NULL,  -- 0 = 书级步骤(l2_global / l1_merge)
    step TEXT NOT NULL CHECK(step IN ('parse','l4','l3','l2_global','l1_merge')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','processing','complete','failed')),
    error_message TEXT,
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(book_id, chapter_id, step)
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_chapters_book ON chapters(book_id, index_num);
CREATE INDEX IF NOT EXISTS idx_atoms_chapter ON atoms(chapter_id, reading_order);
CREATE INDEX IF NOT EXISTS idx_atoms_book ON atoms(book_id, reading_order);
CREATE INDEX IF NOT EXISTS idx_plot_nodes_book ON plot_nodes(book_id, layer, parent_id);
CREATE INDEX IF NOT EXISTS idx_plot_nodes_parent ON plot_nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_processing_state_book ON processing_state(book_id, status);
"""
