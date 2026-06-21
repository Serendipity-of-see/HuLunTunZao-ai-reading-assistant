import json
from datetime import datetime, timezone
from db.connection import get_db


HLTZ_VERSION = 1


async def export_book(book_id: int) -> dict:
    """导出单本书的完整解析结果为 .hltz 格式。"""
    db = await get_db()
    try:
        # ── 书籍元数据 ──
        cursor = await db.execute(
            "SELECT title, author, total_chars, genre_tags, narrative_summary,"
            "       created_at, updated_at FROM books WHERE id = ?",
            (book_id,),
        )
        book_row = dict(await cursor.fetchone())
        if not book_row:
            raise ValueError(f"Book {book_id} not found")

        genre_tags = json.loads(book_row["genre_tags"]) if book_row.get("genre_tags") else []

        # ── 章节 + atoms ──
        cursor = await db.execute(
            "SELECT id, index_num, title FROM chapters WHERE book_id = ? ORDER BY index_num",
            (book_id,),
        )
        chapter_rows = await cursor.fetchall()

        chapters_data = []

        for ch in chapter_rows:
            cursor = await db.execute(
                "SELECT id, reading_order, content FROM atoms WHERE chapter_id = ? ORDER BY reading_order",
                (ch["id"],),
            )
            atom_rows = await cursor.fetchall()
            atoms = []
            for a in atom_rows:
                atoms.append({"reading_order": a["reading_order"], "content": a["content"]})
            chapters_data.append({
                "index": ch["index_num"],
                "title": ch["title"],
                "atoms": atoms,
            })

        # ── plot_nodes（用 reading_order 引用而非 DB id） ──
        cursor = await db.execute(
            "SELECT id, parent_id, layer, title, summary, detail, importance,"
            "       st_label, cross_refs FROM plot_nodes"
            " WHERE book_id = ? AND layer > 0"
            " ORDER BY layer, id",
            (book_id,),
        )
        plot_rows = await cursor.fetchall()

        # 构建 atom_id → (chapter_index, reading_order) 映射
        cursor = await db.execute(
            "SELECT a.id, a.reading_order, c.index_num FROM atoms a "
            "JOIN chapters c ON a.chapter_id = c.id WHERE a.book_id = ?",
            (book_id,),
        )
        atom_ref_map = {r["id"]: [r["index_num"], r["reading_order"]] for r in await cursor.fetchall()}

        # plot_node_id → [[chapter_index, reading_order], ...]
        pn_atom_refs = {}
        for r in plot_rows:
            cursor = await db.execute(
                "SELECT id FROM atoms WHERE plot_node_id = ? ORDER BY reading_order",
                (r["id"],),
            )
            refs = []
            for a in await cursor.fetchall():
                if a["id"] in atom_ref_map:
                    refs.append(atom_ref_map[a["id"]])
            pn_atom_refs[r["id"]] = refs

        # 构建 parent 引用：用 parent 的 min reading_order 定位
        pn_to_idx = {r["id"]: i for i, r in enumerate(plot_rows)}

        plot_data = []
        for r in plot_rows:
            # 转换 cross_refs 的 target_id → target_index
            raw_refs = json.loads(r["cross_refs"]) if r["cross_refs"] else []
            remapped_refs = []
            for cr in raw_refs:
                if cr.get("target_id") in pn_to_idx:
                    cr_copy = {"relation_type": cr.get("relation_type", ""),
                               "description": cr.get("description", ""),
                               "target_index": pn_to_idx[cr["target_id"]]}
                    remapped_refs.append(cr_copy)

            node = {
                "layer": r["layer"],
                "title": r["title"] or "",
                "summary": r["summary"] or "",
                "detail": r["detail"] or "",
                "importance": r["importance"] or 5,
                "st_label": r["st_label"],
                "cross_refs": remapped_refs,
                "atom_refs": pn_atom_refs.get(r["id"], []),
            }
            if r["parent_id"] and r["parent_id"] in pn_to_idx:
                node["parent_index"] = pn_to_idx[r["parent_id"]]
            plot_data.append(node)

        return {
            "hltz_version": HLTZ_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "book": {
                "title": book_row["title"],
                "author": book_row["author"] or "",
                "total_chars": book_row["total_chars"] or 0,
            },
            "run": {
                "label": "默认",
                "profile": "default",
                "model_used": book_row.get("model_used") or "unknown",
                "processing_time": book_row.get("processing_time") or 0,
                "tokens_in": book_row.get("tokens_in") or 0,
                "tokens_out": book_row.get("tokens_out") or 0,
                "created_at": book_row["created_at"],
                "completed_at": book_row["updated_at"],
            },
            "data": {
                "narrative_summary": book_row["narrative_summary"] or "",
                "genre_tags": genre_tags,
                "chapters": chapters_data,
                "plot_nodes": plot_data,
            },
        }

    finally:
        await db.close()
