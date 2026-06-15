import json
from db.connection import get_db


async def get_bubbles(
    book_id: int,
    layer: int = 2,
) -> list[dict]:
    """
    获取气泡流。
    layer: 1=L1事件标题, 2=L2小事件摘要, 3=L3场景摘要
    """
    db = await get_db()
    try:
        query = """
            SELECT pn.*,
                (SELECT COUNT(*) FROM plot_nodes child WHERE child.parent_id = pn.id) as child_count
            FROM plot_nodes pn
            WHERE pn.book_id = ? AND pn.layer = ?
            ORDER BY pn.id
        """
        params = (book_id, layer)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        bubbles = []
        for row in rows:
            row_dict = dict(row)
            # content 按 layer 映射
            if layer == 1:
                content = row_dict.get("title", "")
            elif layer == 2:
                content = row_dict.get("summary", "")
            else:
                content = row_dict.get("detail", "") or row_dict.get("summary", "")

            bubbles.append({
                "id": row_dict["id"],
                "layer": layer,
                "title": row_dict.get("title", ""),
                "content": content,
                "importance": row_dict.get("importance", 5),
                "compress_state": row_dict.get("compress_state", "detail"),
                "story_time_label": row_dict.get("st_label"),
                "child_count": row_dict.get("child_count", 0),
                "has_cross_refs": bool(row_dict.get("cross_refs") and row_dict["cross_refs"] != "[]"),
                "atom_ids": [],
            })

        return bubbles

    finally:
        await db.close()


async def get_bubble_children(book_id: int, node_id: int) -> dict:
    """获取某气泡的子节点 + L3 展开时获取 L4 句子组和原始 atoms"""
    db = await get_db()
    try:
        # 获取当前节点信息
        cursor = await db.execute(
            "SELECT * FROM plot_nodes WHERE id = ? AND book_id = ?",
            (node_id, book_id),
        )
        node = await cursor.fetchone()
        if not node:
            return {"l4_groups": []}

        node_dict = dict(node)
        layer = node_dict["layer"]

        if layer == 3:
            # 展开 L3：获取下属 L4 句子组及其原始 atoms
            cursor = await db.execute(
                """SELECT pn.* FROM plot_nodes pn
                   WHERE pn.parent_id = ? AND pn.layer = 4
                   ORDER BY pn.id""",
                (node_id,),
            )
            l4_rows = await cursor.fetchall()

            groups = []
            for l4 in l4_rows:
                l4_dict = dict(l4)
                # 获取 L4 关联的原始 atoms
                cursor2 = await db.execute(
                    "SELECT id, content FROM atoms WHERE plot_node_id = ? ORDER BY reading_order",
                    (l4_dict["id"],),
                )
                atom_rows = await cursor2.fetchall()
                groups.append({
                    "group_id": l4_dict["id"],
                    "summary": l4_dict.get("summary", ""),
                    "atoms": [{"id": a["id"], "content": a["content"]} for a in atom_rows],
                })

            return {"l4_groups": groups}

        elif layer in (1, 2):
            # 展开 L1 或 L2：返回子节点列表
            child_layer = layer + 1
            cursor = await db.execute(
                """SELECT pn.*,
                    (SELECT COUNT(*) FROM plot_nodes child WHERE child.parent_id = pn.id) as child_count
                   FROM plot_nodes pn
                   WHERE pn.parent_id = ? AND pn.layer = ?
                   ORDER BY pn.id""",
                (node_id, child_layer),
            )
            children = await cursor.fetchall()

            return {
                "children": [
                    {
                        "id": c["id"],
                        "layer": child_layer,
                        "title": c["title"],
                        "content": c["summary"] if child_layer == 2 else (c["detail"] or c["summary"]),
                        "importance": c["importance"],
                        "child_count": c["child_count"],
                    }
                    for c in children
                ]
            }

        return {"l4_groups": []}

    finally:
        await db.close()


async def get_tree(book_id: int) -> list[dict]:
    """返回完整情节树（嵌套）。若无 L1 则从 L2 起步。"""
    db = await get_db()
    try:
        for start_layer in (1, 2):
            cursor = await db.execute(
                """SELECT pn.*, (SELECT COUNT(*) FROM plot_nodes child WHERE child.parent_id = pn.id) as child_count
                   FROM plot_nodes pn WHERE pn.book_id = ? AND pn.layer = ? AND pn.parent_id IS NULL
                   ORDER BY pn.id""",
                (book_id, start_layer),
            )
            roots = await cursor.fetchall()
            if roots: break

        return [await _build_tree(db, dict(r)) for r in roots] if roots else []
    finally:
        await db.close()


async def _build_tree(db, node: dict) -> dict:
    layer, nid = node["layer"], node["id"]
    content = node.get("title") if layer == 1 else (node.get("summary") if layer in (2, 4) else (node.get("detail") or node.get("summary") or ""))
    result = {
        "id": nid, "layer": layer, "title": node.get("title", ""), "content": content,
        "importance": node.get("importance", 5), "story_time_label": node.get("st_label"),
        "child_count": node.get("child_count", 0),
        "has_cross_refs": bool(node.get("cross_refs") and node["cross_refs"] != "[]"),
        "children": [],
    }
    cursor = await db.execute(
        """SELECT pn.*, (SELECT COUNT(*) FROM plot_nodes child WHERE child.parent_id = pn.id) as child_count
           FROM plot_nodes pn WHERE pn.parent_id = ? AND pn.layer = ? ORDER BY pn.id""",
        (nid, layer + 1),
    )
    for child in await cursor.fetchall():
        cd = dict(child)
        if layer == 3:
            # 查询 L4 的第一个 atom 作为跳转锚点
            cursor2 = await db.execute(
                """SELECT a.id, a.reading_order, c.index_num as chapter_index
                   FROM atoms a JOIN chapters c ON a.chapter_id = c.id
                   WHERE a.plot_node_id = ? ORDER BY a.reading_order LIMIT 1""",
                (cd["id"],),
            )
            first = await cursor2.fetchone()
            jump_anchor = None
            if first:
                jump_anchor = {
                    "chapter_index": first["chapter_index"],
                    "atom_id": first["id"],
                    "reading_order": first["reading_order"],
                }
            result["children"].append({
                "id": cd["id"], "layer": 4, "title": cd.get("title", ""),
                "content": cd.get("summary", ""),
                "importance": cd.get("importance", 5), "child_count": 0, "children": [],
                "jump_anchor": jump_anchor,
            })
        else:
            result["children"].append(await _build_tree(db, cd))
    return result
