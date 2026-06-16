import json
import traceback
from agents.parse_agent import parse_book
from agents.plot_agent import PlotAgent
from db.connection import get_db


# ══════════════════════════════════════════════════════════════════════
# 主管线
# ══════════════════════════════════════════════════════════════════════

async def process_book_phase1(book_id: int, file_path: str, reader_mode: str = "new"):
    """
    Phase 1 增量处理管线：
    1. Parse Agent → chapters + atoms
    2. 逐章 L4（AI 语义分组+轻量概括）→ 立即写 DB
    3. 逐章 L3（场景聚合）→ 立即写 DB
    4. 全局 L2（全书 L3 → L2 事件）→ 写 DB
    5. Merge Agent L2→L1 + narrative_summary
    每步处理前查 processing_state，支持断点续处理。
    """
    try:
        parse_result = parse_book(file_path)
        total_chapters = len(parse_result["chapters"])

        # 确定处理范围
        if total_chapters <= 20:
            chapters_to_process = list(range(1, total_chapters + 1))
        elif reader_mode == "new":
            chapters_to_process = [1]
        else:
            chapters_to_process = list(range(1, total_chapters + 1))

        db = await get_db()
        try:
            # ── Step 1: Parse → chapters + atoms ──
            await _step_parse(db, book_id, parse_result, chapters_to_process)

            # ── Step 2: 逐章 L4 ──
            await _step_l4_per_chapter(db, book_id, parse_result, chapters_to_process)

            # ── Step 3: 逐章 L3 ──
            await _step_l3_per_chapter(db, book_id, parse_result, chapters_to_process)

            # ── Step 4: 全局 L2 ──
            await _step_l2_global(db, book_id, chapters_to_process)

            # ── Step 5: Merge L2→L1 ──
            await _step_merge_l1(db, book_id)

            # ── Step 6: 更新统计 ──
            await db.execute(
                "UPDATE books SET total_chars = ?, updated_at = datetime('now') WHERE id = ?",
                (parse_result["total_chars"], book_id),
            )
            await db.commit()
            print(f"[INFO] Book {book_id} fully processed")

        finally:
            await db.close()

    except Exception as e:
        print(f"[ERROR] process_book_phase1 failed for book {book_id}:")
        traceback.print_exc()
        try:
            db2 = await get_db()
            await db2.execute(
                "INSERT OR REPLACE INTO processing_state (book_id, chapter_id, step, status, error_message, updated_at) "
                "VALUES (?, 0, 'parse', 'failed', ?, datetime('now'))",
                (book_id, str(e)[:500]),
            )
            await db2.commit()
            await db2.close()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════
# 管线各步骤
# ══════════════════════════════════════════════════════════════════════

async def _step_parse(db, book_id, parse_result, chapters_to_process):
    """Step 1: 写入 chapters + atoms（幂等）。"""
    existing = await (await db.execute(
        "SELECT COUNT(*) as c FROM chapters WHERE book_id = ?", (book_id,)
    )).fetchone()

    if existing["c"] > 0:
        print(f"[INFO] Book {book_id} already has {existing['c']} chapters, skip parse")
        # 确保所有章的 parse 状态已记录
        for ch_idx in chapters_to_process:
            ch = parse_result["chapters"][ch_idx - 1]
            chapter_db_id = await _get_chapter_db_id(db, book_id, ch["index"])
            if chapter_db_id:
                await _set_state(db, book_id, chapter_db_id, "parse", "complete")
        await db.commit()
        return

    reading_order = 0
    for ch_idx in chapters_to_process:
        ch = parse_result["chapters"][ch_idx - 1]

        cursor = await db.execute(
            "INSERT INTO chapters (book_id, index_num, title) VALUES (?, ?, ?)",
            (book_id, ch["index"], ch["title"]),
        )
        chapter_id = cursor.lastrowid

        atom_data = [
            (chapter_id, book_id, 0, reading_order + i, content)
            for i, content in enumerate(ch["atoms"])
        ]
        await db.executemany(
            "INSERT INTO atoms (chapter_id, book_id, paragraph_id, reading_order, content) "
            "VALUES (?, ?, ?, ?, ?)",
            atom_data,
        )
        reading_order += len(ch["atoms"])

        await _set_state(db, book_id, chapter_id, "parse", "complete")

    await db.commit()
    print(f"[INFO] Parse complete: {len(chapters_to_process)} chapters written")


async def _step_l4_per_chapter(db, book_id, parse_result, chapters_to_process):
    """Step 2: 逐章 L4 语义分组+轻量概括。"""
    plot_agent = PlotAgent()
    processed, skipped = 0, 0

    for ch_idx in chapters_to_process:
        ch = parse_result["chapters"][ch_idx - 1]
        chapter_db_id = await _get_chapter_db_id(db, book_id, ch["index"])
        if not chapter_db_id:
            continue

        status = await _get_state(db, book_id, chapter_db_id, "l4")
        if status == "complete":
            skipped += 1
            continue
        if status == "failed":
            print(f"  [INFO] Chapter {ch['index']} L4 previously failed, skip (use retry)")
            skipped += 1
            continue
        if status == "processing":
            # 上次崩溃，清理残留后重跑
            await _cleanup_layer(db, book_id, chapter_db_id, 4)
            print(f"  [INFO] Chapter {ch['index']} L4 was in-progress, cleaning up and retrying")

        # 加载 atoms
        atoms = await _load_atoms_for_chapter(db, book_id, ch["index"])
        if not atoms:
            continue

        await _set_state(db, book_id, chapter_db_id, "l4", "processing")
        await db.commit()

        print(f"[INFO] L4: chapter {ch['index']}/{len(parse_result['chapters'])} ({len(atoms)} atoms)...")
        try:
            l4_groups, genre_tags = await plot_agent.process_chapter_l4(ch["index"], atoms)
            if l4_groups:
                await _write_l4_incremental(db, book_id, l4_groups)
                # 首次保存 genre_tags
                if genre_tags:
                    existing = await (await db.execute(
                        "SELECT genre_tags FROM books WHERE id=?", (book_id,)
                    )).fetchone()
                    if existing and (not existing["genre_tags"] or existing["genre_tags"] == "[]"):
                        await db.execute("UPDATE books SET genre_tags=? WHERE id=?",
                                         (json.dumps(genre_tags), book_id))
            await _set_state(db, book_id, chapter_db_id, "l4", "complete")
            await db.commit()
            processed += 1
            print(f"  [INFO] Chapter {ch['index']} L4 done: {len(l4_groups)} groups")
        except Exception as e:
            await _set_state(db, book_id, chapter_db_id, "l4", "failed", str(e))
            await db.commit()
            print(f"  [ERROR] Chapter {ch['index']} L4 failed: {e}")

    print(f"[INFO] L4 pass: {processed} processed, {skipped} skipped")


async def _step_l3_per_chapter(db, book_id, parse_result, chapters_to_process):
    """Step 3: 逐章 L3 场景聚合。"""
    plot_agent = PlotAgent()
    processed, skipped = 0, 0

    for ch_idx in chapters_to_process:
        ch = parse_result["chapters"][ch_idx - 1]
        chapter_db_id = await _get_chapter_db_id(db, book_id, ch["index"])
        if not chapter_db_id:
            continue

        status = await _get_state(db, book_id, chapter_db_id, "l3")
        if status == "complete":
            skipped += 1
            continue
        if status == "failed":
            skipped += 1
            continue
        if status == "processing":
            await _cleanup_layer(db, book_id, chapter_db_id, 3)
            print(f"  [INFO] Chapter {ch['index']} L3 was in-progress, cleaning up and retrying")

        # 加载该章的 L4 groups
        l4_groups = await _load_l4_groups_for_chapter(db, book_id, ch["index"])
        if not l4_groups:
            print(f"  [WARN] Chapter {ch['index']}: no L4 groups, run L4 first")
            continue

        await _set_state(db, book_id, chapter_db_id, "l3", "processing")
        await db.commit()

        print(f"[INFO] L3: chapter {ch['index']}/{len(parse_result['chapters'])} ({len(l4_groups)} L4 groups)...")
        try:
            l3_scenes = await plot_agent.process_chapter_l3(ch["index"], l4_groups)
            if l3_scenes:
                await _write_l3_incremental(db, book_id, l4_groups, l3_scenes)
            await _set_state(db, book_id, chapter_db_id, "l3", "complete")
            await db.commit()
            processed += 1
            print(f"  [INFO] Chapter {ch['index']} L3 done: {len(l3_scenes)} scenes")
        except Exception as e:
            await _set_state(db, book_id, chapter_db_id, "l3", "failed", str(e))
            await db.commit()
            print(f"  [ERROR] Chapter {ch['index']} L3 failed: {e}")

    print(f"[INFO] L3 pass: {processed} processed, {skipped} skipped")


async def _step_l2_global(db, book_id, chapters_to_process):
    """Step 4: 全局 L2（所有章 L3 齐全后）。"""
    # 检查所有目标章的 L3 是否完成
    all_l3_done = True
    for ch_idx in chapters_to_process:
        ch_db_id = await _get_chapter_db_id(db, book_id, ch_idx)
        if ch_db_id:
            s = await _get_state(db, book_id, ch_db_id, "l3")
            if s != "complete":
                all_l3_done = False
                break

    if not all_l3_done:
        print("[INFO] L2: not all chapters have L3 complete, deferring")
        return

    status = await _get_state(db, book_id, 0, "l2_global")
    if status == "complete":
        print("[INFO] L2 global already complete, skip")
        return
    if status == "processing":
        await _cleanup_layer(db, book_id, 0, 2)
        print("[INFO] L2 global was in-progress, cleaning up and retrying")

    all_l3 = await _load_all_l3_scenes(db, book_id)
    if not all_l3:
        print("[WARN] No L3 scenes found, skip L2")
        return

    await _set_state(db, book_id, 0, "l2_global", "processing")
    await db.commit()

    print(f"[INFO] L2 global: aggregating {len(all_l3)} L3 scenes across all chapters...")
    plot_agent = PlotAgent()
    try:
        l2_events = await plot_agent.process_l2_global(all_l3)
        if l2_events:
            await _write_l2_global(db, book_id, all_l3, l2_events)
        await _set_state(db, book_id, 0, "l2_global", "complete")
        await db.commit()
        print(f"[INFO] L2 global done: {len(l2_events)} events")
    except Exception as e:
        await _set_state(db, book_id, 0, "l2_global", "failed", str(e))
        await db.commit()
        print(f"[ERROR] L2 global failed: {e}")


async def _step_merge_l1(db, book_id):
    """Step 5: Merge Agent L2→L1。"""
    status = await _get_state(db, book_id, 0, "l1_merge")
    if status == "complete":
        print("[INFO] L1 merge already complete, skip")
        return

    cursor = await db.execute(
        "SELECT id, title, summary, importance FROM plot_nodes WHERE book_id=? AND layer=2 AND parent_id IS NULL",
        (book_id,),
    )
    l2_rows = await cursor.fetchall()
    if not l2_rows:
        print("[INFO] No un-parented L2 nodes, skip merge")
        await _set_state(db, book_id, 0, "l1_merge", "complete")
        await db.commit()
        return

    l2_nodes = [{"id": r["id"], "title": r["title"], "summary": r["summary"], "importance": r["importance"]}
                for r in l2_rows]
    print(f"[INFO] Merge Agent: aggregating {len(l2_nodes)} L2 nodes...")

    from agents.merge_agent import MergeAgent
    merge = MergeAgent()
    try:
        merge_result = await merge.aggregate(book_id, l2_nodes)

        for l1 in merge_result.get("layer_1_events", []):
            cursor = await db.execute(
                """INSERT INTO plot_nodes (book_id, layer, node_type, title, summary, detail, importance, st_label)
                   VALUES (?, 1, 'plot', ?, ?, ?, ?, ?)""",
                (book_id, l1.get("title", ""), l1.get("summary", ""), "",
                 l1.get("importance", 7), l1.get("story_time_label", "")),
            )
            l1_id = cursor.lastrowid
            for l2_id in l1.get("parent_l2_ids", []):
                await db.execute("UPDATE plot_nodes SET parent_id=? WHERE id=?", (l1_id, l2_id))

        ns = merge_result.get("narrative_summary", "")
        if ns:
            await db.execute("UPDATE books SET narrative_summary=? WHERE id=?", (ns, book_id))

        await _set_state(db, book_id, 0, "l1_merge", "complete")
        await db.commit()
        print(f"[INFO] Merge done: {len(merge_result.get('layer_1_events', []))} L1 events")
    except Exception as e:
        await _set_state(db, book_id, 0, "l1_merge", "failed", str(e))
        await db.commit()
        print(f"[ERROR] Merge failed: {e}")


# ══════════════════════════════════════════════════════════════════════
# 增量写入辅助函数
# ══════════════════════════════════════════════════════════════════════

async def _write_l4_incremental(db, book_id, l4_groups):
    """写入 L4 plot_nodes + 更新 atoms.plot_node_id。"""
    for g_idx, group in enumerate(l4_groups):
        atom_ids = group.get("atom_ids", [])
        if not atom_ids:
            continue
        summary = group.get("summary", "")
        title = _safe_truncate(summary, 20) if summary else f"句组{g_idx+1}"
        cursor = await db.execute(
            "INSERT INTO plot_nodes (book_id, layer, node_type, title, summary, importance) VALUES (?, 4, 'plot', ?, ?, 5)",
            (book_id, title, summary),
        )
        l4_id = cursor.lastrowid
        for aid in atom_ids:
            await db.execute("UPDATE atoms SET plot_node_id = ? WHERE id = ?", (l4_id, aid))


async def _write_l3_incremental(db, book_id, l4_groups, l3_scenes):
    """写入 L3 plot_nodes + 回填 L4→L3 父子关系。l4_groups 需含 atom_ids 以定位 L4 DB ID。"""
    # 批量查询 atom_id → l4_db_id
    all_aids = [aid for g in l4_groups for aid in g.get("atom_ids", [])]
    atom_to_l4 = {}
    if all_aids:
        placeholders = ",".join("?" * len(all_aids))
        cursor = await db.execute(
            f"SELECT id, plot_node_id FROM atoms WHERE id IN ({placeholders})",
            all_aids,
        )
        for r in await cursor.fetchall():
            if r["plot_node_id"]:
                atom_to_l4[r["id"]] = r["plot_node_id"]

    l3_db_ids = {}
    for idx, scene in enumerate(l3_scenes):
        cursor = await db.execute(
            """INSERT INTO plot_nodes (book_id, layer, node_type, title, summary, importance, st_label)
               VALUES (?, 3, 'plot', ?, ?, ?, ?)""",
            (book_id, scene.get("title", ""), scene.get("summary", ""),
             scene.get("importance", 5), scene.get("story_time_label", "")),
        )
        l3_db_id = cursor.lastrowid
        l3_db_ids[idx] = l3_db_id

        # 回填 L4 → L3
        done_l4 = set()
        for l4_idx in scene.get("parent_l4_indices", []):
            if l4_idx < len(l4_groups):
                for aid in l4_groups[l4_idx].get("atom_ids", []):
                    l4_db_id = atom_to_l4.get(aid)
                    if l4_db_id and l4_db_id not in done_l4:
                        done_l4.add(l4_db_id)
                        await db.execute("UPDATE plot_nodes SET parent_id=? WHERE id=?", (l3_db_id, l4_db_id))


async def _write_l2_global(db, book_id, all_l3, l2_events):
    """写入全局 L2 plot_nodes + 回填 L3→L2。all_l3 每项含 db_id 字段。"""
    # all_l3: [{global_index, db_id, ...}]
    l3_id_map = {s["global_index"]: s["db_id"] for s in all_l3}

    for event in l2_events:
        cross_refs = event.get("cross_refs", [])
        cursor = await db.execute(
            """INSERT INTO plot_nodes (book_id, layer, node_type, title, summary, importance, st_label, cross_refs)
               VALUES (?, 2, 'plot', ?, ?, ?, ?, ?)""",
            (book_id, event.get("title", ""), event.get("summary", ""),
             event.get("importance", 5), event.get("story_time_label", ""), json.dumps(cross_refs)),
        )
        l2_db_id = cursor.lastrowid
        for l3_idx in event.get("parent_l3_indices", []):
            l3_db_id = l3_id_map.get(l3_idx)
            if l3_db_id:
                await db.execute("UPDATE plot_nodes SET parent_id=? WHERE id=?", (l2_db_id, l3_db_id))

    # L0 根节点
    cursor = await db.execute("SELECT id FROM plot_nodes WHERE book_id=? AND layer=0", (book_id,))
    if not await cursor.fetchone():
        await db.execute(
            "INSERT INTO plot_nodes (book_id, layer, node_type, title, summary) VALUES (?, 0, 'plot', '全书根', '')",
            (book_id,),
        )


# ══════════════════════════════════════════════════════════════════════
# 数据加载辅助函数
# ══════════════════════════════════════════════════════════════════════

async def _load_atoms_for_chapter(db, book_id, chapter_index):
    """加载一章的 atoms。"""
    cursor = await db.execute(
        "SELECT a.id, a.content FROM atoms a "
        "JOIN chapters c ON a.chapter_id = c.id "
        "WHERE a.book_id = ? AND c.index_num = ? "
        "ORDER BY a.reading_order",
        (book_id, chapter_index),
    )
    return [{"id": r["id"], "content": r["content"]} for r in await cursor.fetchall()]


async def _load_l4_groups_for_chapter(db, book_id, chapter_index):
    """加载一章的 L4 分组摘要（按 atom 阅读顺序）。"""
    cursor = await db.execute(
        """SELECT DISTINCT pn.id, pn.summary, pn.title,
           (SELECT MIN(a2.reading_order) FROM atoms a2 WHERE a2.plot_node_id = pn.id) as min_order
           FROM plot_nodes pn
           JOIN atoms a ON a.plot_node_id = pn.id
           JOIN chapters c ON a.chapter_id = c.id
           WHERE pn.book_id = ? AND pn.layer = 4 AND c.index_num = ?
           ORDER BY min_order""",
        (book_id, chapter_index),
    )
    rows = await cursor.fetchall()
    # 同时获取每个 L4 的 atom_ids
    result = []
    for i, r in enumerate(rows):
        cursor2 = await db.execute(
            "SELECT id FROM atoms WHERE plot_node_id = ? ORDER BY reading_order",
            (r["id"],),
        )
        atom_ids = [a["id"] for a in await cursor2.fetchall()]
        result.append({
            "group_index": i,
            "summary": r["summary"] or "",
            "atom_ids": atom_ids,
        })
    return result


async def _load_all_l3_scenes(db, book_id):
    """加载全书 L3 场景（用于全局 L2）。返回 [{global_index, chapter_index, db_id, title, summary, importance}]。"""
    cursor = await db.execute(
        """SELECT pn.id, pn.title, pn.summary, pn.importance,
           (SELECT MIN(c.index_num) FROM atoms a JOIN chapters c ON a.chapter_id = c.id WHERE a.plot_node_id IN
            (SELECT l4.id FROM plot_nodes l4 WHERE l4.parent_id = pn.id)) as chapter_index
           FROM plot_nodes pn
           WHERE pn.book_id = ? AND pn.layer = 3
           ORDER BY chapter_index, pn.id""",
        (book_id,),
    )
    rows = await cursor.fetchall()
    return [
        {
            "global_index": i,
            "chapter_index": r["chapter_index"] or "?",
            "db_id": r["id"],
            "title": r["title"] or "",
            "summary": r["summary"] or "",
            "importance": r["importance"] or 5,
        }
        for i, r in enumerate(rows)
    ]


# ══════════════════════════════════════════════════════════════════════
# processing_state 操作
# ══════════════════════════════════════════════════════════════════════

async def _get_chapter_db_id(db, book_id, chapter_index):
    """根据 chapter_index 获取 chapter 的 DB id。"""
    cursor = await db.execute(
        "SELECT id FROM chapters WHERE book_id = ? AND index_num = ?",
        (book_id, chapter_index),
    )
    row = await cursor.fetchone()
    return row["id"] if row else None


async def _get_state(db, book_id, chapter_id, step):
    """读取处理状态。"""
    cursor = await db.execute(
        "SELECT status FROM processing_state WHERE book_id=? AND chapter_id=? AND step=?",
        (book_id, chapter_id, step),
    )
    row = await cursor.fetchone()
    return row["status"] if row else "pending"


async def _set_state(db, book_id, chapter_id, step, status, error=None):
    """写入处理状态。"""
    await db.execute(
        """INSERT OR REPLACE INTO processing_state (book_id, chapter_id, step, status, error_message, updated_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))""",
        (book_id, chapter_id, step, status, error),
    )


async def _cleanup_layer(db, book_id, chapter_id, layer):
    """清除某章/某层的残留数据。
    - layer=4: 删该章 atoms 关联的 L4 plot_nodes，重置 atom.plot_node_id
    - layer=3: 删该章 L4 的父 L3 plot_nodes（以及 L3 的父 L2），重置 parent_id
    - layer=2: 删全书 L2（chapter_id=0 时），重置 L3.parent_id
    """
    if layer == 4:
        # 获取该章 atoms 关联的 L4
        cursor = await db.execute(
            """SELECT DISTINCT pn.id FROM plot_nodes pn
               JOIN atoms a ON a.plot_node_id = pn.id
               JOIN chapters c ON a.chapter_id = c.id
               WHERE pn.book_id=? AND pn.layer=4 AND c.id=?""",
            (book_id, chapter_id),
        )
        l4_ids = [r["id"] for r in await cursor.fetchall()]
        if l4_ids:
            placeholders = ",".join("?" * len(l4_ids))
            await db.execute(
                f"UPDATE atoms SET plot_node_id = NULL WHERE plot_node_id IN ({placeholders})",
                l4_ids,
            )
            await db.execute(
                f"DELETE FROM plot_nodes WHERE id IN ({placeholders})",
                l4_ids,
            )
    elif layer == 3:
        # 清除该章 L4 → L3 的 parent 关系，删 L3
        cursor = await db.execute(
            """SELECT DISTINCT l3.id FROM plot_nodes l3
               JOIN plot_nodes l4 ON l4.parent_id = l3.id AND l4.layer = 4
               JOIN atoms a ON a.plot_node_id = l4.id
               WHERE l3.book_id=? AND l3.layer=3 AND a.chapter_id=?""",
            (book_id, chapter_id),
        )
        l3_ids = [r["id"] for r in await cursor.fetchall()]
        if l3_ids:
            placeholders = ",".join("?" * len(l3_ids))
            await db.execute(
                f"UPDATE plot_nodes SET parent_id = NULL WHERE parent_id IN ({placeholders})",
                l3_ids,
            )
            await db.execute(
                f"DELETE FROM plot_nodes WHERE id IN ({placeholders})",
                l3_ids,
            )
    elif layer == 2:
        await db.execute(
            "UPDATE plot_nodes SET parent_id = NULL WHERE book_id=? AND layer=3 AND parent_id IS NOT NULL",
            (book_id,),
        )
        await db.execute(
            "DELETE FROM plot_nodes WHERE book_id=? AND layer=2",
            (book_id,),
        )


def _safe_truncate(text: str, max_len: int) -> str:
    """安全截断中文文本，尽量在句末标点处断开。"""
    if len(text) <= max_len:
        return text
    for punct in "。！？；，、":
        idx = text.rfind(punct, 0, max_len)
        if idx > max_len // 2:
            return text[:idx + 1]
    return text[:max_len]


# ══════════════════════════════════════════════════════════════════════
# 旧数据迁移
# ══════════════════════════════════════════════════════════════════════

async def migrate_processing_state():
    """回填旧数据的 processing_state。已有 plot_nodes 的书标记为 complete。"""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM processing_state")
        row = await cursor.fetchone()
        if row["cnt"] > 0:
            print("[MIGRATION] processing_state already populated, skip")
            return

        cursor = await db.execute("""
            SELECT DISTINCT b.id FROM books b
            JOIN chapters c ON b.id = c.book_id
            WHERE b.id NOT IN (SELECT DISTINCT book_id FROM processing_state)
        """)
        legacy_books = await cursor.fetchall()

        for book in legacy_books:
            book_id = book["id"]

            await db.execute(
                """INSERT OR IGNORE INTO processing_state (book_id, chapter_id, step, status)
                   SELECT ?, id, 'parse', 'complete' FROM chapters WHERE book_id = ?""",
                (book_id, book_id),
            )

            cursor2 = await db.execute(
                "SELECT DISTINCT a.chapter_id FROM atoms a WHERE a.book_id = ? AND a.plot_node_id IS NOT NULL",
                (book_id,),
            )
            l4_chapters = {r["chapter_id"] for r in await cursor2.fetchall()}
            for ch_id in l4_chapters:
                await db.execute(
                    "INSERT OR IGNORE INTO processing_state (book_id, chapter_id, step, status) VALUES (?, ?, 'l4', 'complete')",
                    (book_id, ch_id),
                )

            cursor3 = await db.execute(
                """SELECT DISTINCT a.chapter_id FROM atoms a
                   JOIN plot_nodes l4 ON a.plot_node_id = l4.id
                   JOIN plot_nodes l3 ON l4.parent_id = l3.id AND l3.layer = 3
                   WHERE a.book_id = ?""",
                (book_id,),
            )
            l3_chapters = {r["chapter_id"] for r in await cursor3.fetchall()}
            for ch_id in l3_chapters:
                await db.execute(
                    "INSERT OR IGNORE INTO processing_state (book_id, chapter_id, step, status) VALUES (?, ?, 'l3', 'complete')",
                    (book_id, ch_id),
                )

            cursor4 = await db.execute(
                "SELECT COUNT(*) as cnt FROM plot_nodes WHERE book_id = ? AND layer = 2",
                (book_id,),
            )
            if (await cursor4.fetchone())["cnt"] > 0:
                await db.execute(
                    "INSERT OR IGNORE INTO processing_state (book_id, chapter_id, step, status) VALUES (?, 0, 'l2_global', 'complete')",
                    (book_id,),
                )

            cursor5 = await db.execute(
                "SELECT COUNT(*) as cnt FROM plot_nodes WHERE book_id = ? AND layer = 1",
                (book_id,),
            )
            if (await cursor5.fetchone())["cnt"] > 0:
                await db.execute(
                    "INSERT OR IGNORE INTO processing_state (book_id, chapter_id, step, status) VALUES (?, 0, 'l1_merge', 'complete')",
                    (book_id,),
                )

        await db.commit()
        print(f"[MIGRATION] Backfilled processing_state for {len(legacy_books)} legacy books")
    finally:
        await db.close()
