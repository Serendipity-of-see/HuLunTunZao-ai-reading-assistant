import json
from db.connection import get_db


HLTZ_VERSION = 1


async def import_hltz(data: dict) -> int:
    """从 .hltz JSON 导入书籍，写入 DB。返回 book_id。"""
    if data.get("hltz_version") != HLTZ_VERSION:
        raise ValueError(f"不支持的 .hltz 版本: {data.get('hltz_version')}")

    book_info = data.get("book", {})
    content = data.get("data", {})

    db = await get_db()
    try:
        await db.execute("BEGIN")
        # ── 创建书籍 ──
        run_info = data.get("run", {})
        genre_tags = json.dumps(content.get("genre_tags", []))
        cursor = await db.execute(
            """INSERT INTO books (title, author, total_chars, genre_tags, narrative_summary,
               processing_time, tokens_in, tokens_out, model_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                book_info.get("title", "未命名"),
                book_info.get("author", ""),
                book_info.get("total_chars", 0),
                genre_tags,
                content.get("narrative_summary", ""),
                run_info.get("processing_time", 0),
                run_info.get("tokens_in", 0),
                run_info.get("tokens_out", 0),
                run_info.get("model_used", ""),
            ),
        )
        book_id = cursor.lastrowid

        # ── 写入章节 + atoms ──
        atom_id_map = {}  # (chapter_index, reading_order) → db_atom_id
        for ch in content.get("chapters", []):
            cursor = await db.execute(
                "INSERT INTO chapters (book_id, index_num, title) VALUES (?, ?, ?)",
                (book_id, ch["index"], ch.get("title", "")),
            )
            chapter_db_id = cursor.lastrowid

            atoms = ch.get("atoms", [])
            if atoms:
                atom_data = [
                    (chapter_db_id, book_id, 0, a["reading_order"], a["content"])
                    for a in atoms
                ]
                await db.executemany(
                    "INSERT INTO atoms (chapter_id, book_id, paragraph_id, reading_order, content)"
                    " VALUES (?, ?, ?, ?, ?)",
                    atom_data,
                )

            # 获取刚插入的 atom ids
            cursor = await db.execute(
                "SELECT id, reading_order FROM atoms WHERE chapter_id = ? ORDER BY reading_order",
                (chapter_db_id,),
            )
            for a in await cursor.fetchall():
                atom_id_map[(ch["index"], a["reading_order"])] = a["id"]

        # ── 写入 plot_nodes ──
        idx_to_db_id = {}  # plot_data 数组索引 → DB id
        for i, pn in enumerate(content.get("plot_nodes", [])):
            cursor = await db.execute(
                """INSERT INTO plot_nodes (book_id, layer, node_type, title, summary, detail,
                   importance, st_label, cross_refs)
                   VALUES (?, ?, 'plot', ?, ?, ?, ?, ?, ?)""",
                (
                    book_id,
                    pn.get("layer", 4),
                    pn.get("title", ""),
                    pn.get("summary", ""),
                    pn.get("detail", ""),
                    pn.get("importance", 5),
                    pn.get("st_label", ""),
                    json.dumps(pn.get("cross_refs", [])),
                ),
            )
            pn_db_id = cursor.lastrowid
            idx_to_db_id[i] = pn_db_id

            # 回填 atoms.plot_node_id（atom_refs: [[chapter_index, reading_order], ...]）
            for ref in pn.get("atom_refs", []):
                ch_idx, rd_ord = ref[0], ref[1]
                key = (ch_idx, rd_ord)
                if key in atom_id_map:
                    await db.execute(
                        "UPDATE atoms SET plot_node_id = ? WHERE id = ?",
                        (pn_db_id, atom_id_map[key]),
                    )

        # ── 回填 parent_id ──
        for i, pn in enumerate(content.get("plot_nodes", [])):
            if "parent_index" in pn and pn["parent_index"] in idx_to_db_id:
                await db.execute(
                    "UPDATE plot_nodes SET parent_id = ? WHERE id = ?",
                    (idx_to_db_id[pn["parent_index"]], idx_to_db_id[i]),
                )

        # ── 回填 cross_refs（target_index → target_id） ──
        for i, pn in enumerate(content.get("plot_nodes", [])):
            raw_refs = pn.get("cross_refs", [])
            if not raw_refs:
                continue
            remapped = []
            for cr in raw_refs:
                ti = cr.get("target_index")
                if ti is not None and ti in idx_to_db_id:
                    remapped.append({
                        "target_id": idx_to_db_id[ti],
                        "relation_type": cr.get("relation_type", ""),
                        "description": cr.get("description", ""),
                    })
            if remapped:
                await db.execute(
                    "UPDATE plot_nodes SET cross_refs = ? WHERE id = ?",
                    (json.dumps(remapped), idx_to_db_id[i]),
                )

        # ── 初始化阅读进度 + L0 根节点 ──
        await db.execute(
            "INSERT INTO reading_progress (book_id, atom_position) VALUES (?, 0)",
            (book_id,),
        )
        await db.execute(
            "INSERT INTO plot_nodes (book_id, layer, node_type, title, summary)"
            " VALUES (?, 0, 'plot', '全书根', '')",
            (book_id,),
        )

        # ── 标记所有处理步骤为 complete ──
        for ch in content.get("chapters", []):
            cursor = await db.execute(
                "SELECT id FROM chapters WHERE book_id = ? AND index_num = ?",
                (book_id, ch["index"]),
            )
            row = await cursor.fetchone()
            if row:
                for step in ("parse", "l4", "l3"):
                    await db.execute(
                        "INSERT INTO processing_state (book_id, chapter_id, step, status) VALUES (?, ?, ?, 'complete')",
                        (book_id, row["id"], step),
                    )
        for step in ("l2_global", "l1_merge"):
            await db.execute(
                "INSERT INTO processing_state (book_id, chapter_id, step, status) VALUES (?, 0, ?, 'complete')",
                (book_id, step),
            )

        await db.commit()
        return book_id

    except Exception:
        await db.rollback()
        raise
    finally:
        await db.close()
