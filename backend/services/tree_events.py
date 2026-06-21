"""L4/L3 写完数据后推增量事件给 tracker。"""

async def push_l4_adds(db, book_id, l4_groups, tracker):
    """每个新 L4 组推一个 node_add 事件。"""
    for g in l4_groups:
        atom_ids = g.get("atom_ids", [])
        if not atom_ids:
            continue
        cursor = await db.execute(
            "SELECT plot_node_id FROM atoms WHERE id=?", (atom_ids[0],))
        row = await cursor.fetchone()
        if not row or not row["plot_node_id"]:
            continue
        l4_id = row["plot_node_id"]
        cursor2 = await db.execute("SELECT * FROM plot_nodes WHERE id=?", (l4_id,))
        n = await cursor2.fetchone()
        if not n:
            continue
        nd = dict(n)
        cursor3 = await db.execute(
            "SELECT a.id, a.reading_order, c.index_num as chapter_index "
            "FROM atoms a JOIN chapters c ON a.chapter_id=c.id "
            "WHERE a.plot_node_id=? ORDER BY a.reading_order LIMIT 1", (l4_id,))
        anchor = await cursor3.fetchone()
        node = {
            "id": nd["id"], "layer": 4, "title": nd.get("title", ""),
            "content": nd.get("summary", ""), "importance": nd.get("importance", 5),
            "story_time_label": nd.get("st_label"), "child_count": 0,
            "has_cross_refs": False, "cross_refs": [], "children": [],
            "jump_anchor": {
                "chapter_index": anchor["chapter_index"],
                "atom_id": anchor["id"], "reading_order": anchor["reading_order"],
            } if anchor else None,
        }
        tracker.push(book_id, {"type": "node_add", "parent_id": nd.get("parent_id"), "node": node})


async def push_l3_add(db, book_id, l3_scene, l3_db_id, tracker):
    """新建 L3 场景时推 node_add 事件。"""
    cursor = await db.execute("SELECT * FROM plot_nodes WHERE id=?", (l3_db_id,))
    n = await cursor.fetchone()
    if not n:
        return
    nd = dict(n)
    node = {
        "id": nd["id"], "layer": 3, "title": nd.get("title", ""),
        "content": nd.get("summary", ""), "importance": nd.get("importance", 5),
        "story_time_label": nd.get("st_label"), "child_count": nd.get("child_count", 0),
        "has_cross_refs": False, "cross_refs": [], "children": [],
    }
    tracker.push(book_id, {"type": "node_add", "parent_id": nd.get("parent_id"), "node": node})


async def push_l4_deletes(db, book_id, l4_groups, l4_indices, tracker):
    """L4 被迁走时推 node_delete 事件。"""
    all_aids = [aid for idx in l4_indices if idx < len(l4_groups)
                for aid in l4_groups[idx].get("atom_ids", [])]
    if not all_aids:
        return
    placeholders = ",".join("?" * len(all_aids))
    cursor = await db.execute(
        f"SELECT DISTINCT plot_node_id FROM atoms WHERE id IN ({placeholders})", all_aids)
    done = set()
    async for r in cursor:
        l4_id = r["plot_node_id"]
        if l4_id and l4_id not in done:
            done.add(l4_id)
            tracker.push(book_id, {"type": "node_delete", "node_id": l4_id})
