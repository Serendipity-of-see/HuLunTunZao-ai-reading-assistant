import json
import asyncio
import time
import traceback
from agents.parse_agent import parse_book
from agents.l4_agent import process_l4
from agents.l3_agent import process_single_l3
from agents.l2_agent import process_l2
from db.connection import get_db
from services.progress_tracker import tracker
from services.tree_events import push_l4_adds, push_l3_add, push_l4_deletes


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
    t0 = time.time()
    pipeline_tokens = {"in": 0, "out": 0}
    try:
        # 续传时原文件可能已删除，从 DB 重建
        db0 = await get_db()
        try:
            row = await (await db0.execute(
                "SELECT COUNT(*) as c FROM chapters WHERE book_id=?", (book_id,)
            )).fetchone()
            has_chapters = row["c"] > 0 if row else False
        finally:
            await db0.close()

        if has_chapters:
            parse_result = {"chapters": [], "title": "", "total_chars": 0}
            db1 = await get_db()
            try:
                c_cursor = await db1.execute(
                    "SELECT id, index_num, title FROM chapters WHERE book_id=? ORDER BY index_num", (book_id,))
                for ch in await c_cursor.fetchall():
                    atoms = []
                    a_cursor = await db1.execute(
                        "SELECT content FROM atoms WHERE chapter_id=? ORDER BY reading_order", (ch["id"],))
                    async for a in a_cursor:
                        atoms.append(a["content"])
                    parse_result["chapters"].append({
                        "index": ch["index_num"], "title": ch["title"], "atoms": atoms,
                    })
                    parse_result["total_chars"] += sum(len(a) for a in atoms)
                parse_result["title"] = parse_result["chapters"][0]["title"] if parse_result["chapters"] else ""
            finally:
                await db1.close()
        else:
            parse_result = parse_book(file_path)

        total_chapters = len(parse_result["chapters"])
        tracker.push(book_id, {"type": "context", "total_chapters": total_chapters,
                                "book_title": parse_result.get("title", "")[:30]})

        # 续传时回填已完成步骤，前端进度从正确位置开始
        db_check = await get_db()
        try:
            for step_key in ("parse", "l4", "l3", "l2_global", "l1_merge"):
                row = await (await db_check.execute(
                    "SELECT COUNT(*) as cnt FROM processing_state WHERE book_id=? AND step=? AND status='complete'",
                    (book_id, step_key),
                )).fetchone()
                if row and row["cnt"] > 0:
                    tracker.push(book_id, {"type": "step_complete", "step": step_key})
        finally:
            await db_check.close()

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

            # 创建占位节点（树立即可见）
            await _create_placeholders(db, book_id, chapters_to_process)

            # ── Step 2: 逐章 L4 ──
            await _step_l4_per_chapter(db, book_id, parse_result, chapters_to_process, pipeline_tokens)

            # ── Step 3: 逐章 L3 ──
            await _step_l3_per_chapter(db, book_id, parse_result, chapters_to_process, pipeline_tokens)

            # ── Step 4: 全局 L2 ──
            await _step_l2_global(db, book_id, chapters_to_process)

            # ── Step 5: Merge L2→L1 ──
            await _step_merge_l1(db, book_id)

            # ── Step 6: 更新统计（全跳过时不覆盖已有值）──
            if pipeline_tokens["in"] > 0 or pipeline_tokens["out"] > 0:
                total_elapsed = time.time() - t0
                models_used = "deepseek-v4-flash"
                await db.execute(
                    """UPDATE books SET total_chars=?, updated_at=datetime('now'),
                       processing_time=?, tokens_in=?, tokens_out=?, model_used=?
                       WHERE id=?""",
                    (parse_result["total_chars"], round(total_elapsed, 1),
                     pipeline_tokens["in"], pipeline_tokens["out"], models_used, book_id),
                )
                await db.commit()
                print(f"[INFO] Book {book_id} fully processed")
                tracker.push(book_id, {
                    "type": "stats",
                    "total_elapsed": round(total_elapsed, 1),
                    "total_tokens_in": pipeline_tokens["in"],
                    "total_tokens_out": pipeline_tokens["out"],
                })
            else:
                # 全步骤已完成，清理残留 pending 并更新时间戳
                await db.execute(
                    "DELETE FROM processing_state WHERE book_id=? AND status='pending'", (book_id,))
                await db.execute(
                    "UPDATE books SET updated_at=datetime('now') WHERE id=?", (book_id,))
                await db.commit()
            tracker.push(book_id, {"type": "complete"})

        finally:
            await db.close()

    except asyncio.CancelledError:
        tracker.push(book_id, {"type": "error", "step": "pipeline", "message": "任务被取消"})
        # 清理 processing_state，确保可断点续处理
        try:
            db2 = await get_db()
            await db2.execute(
                "UPDATE processing_state SET status='pending', error_message=NULL "
                "WHERE book_id=? AND status='processing'",
                (book_id,),
            )
            await db2.commit()
            await db2.close()
        except Exception:
            pass
        raise
    except Exception as e:
        print(f"[ERROR] process_book_phase1 failed for book {book_id}:")
        traceback.print_exc()
        tracker.push(book_id, {"type": "error", "step": "pipeline", "message": str(e)[:200]})
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
# 占位节点 — 让档案树在解析初期就可见
# ══════════════════════════════════════════════════════════════════════

async def _create_placeholders(db, book_id, chapters_to_process):
    """创建完整占位链：L0根 + L0-PH + L0-SUM + L1 + L2 + 每章L3。
    已存在则跳过，确保 retry 时树结构完整。"""
    # L0 根
    l0 = await (await db.execute(
        "SELECT id FROM plot_nodes WHERE book_id=? AND layer=0", (book_id,)
    )).fetchone()
    if not l0:
        c = await db.execute(
            "INSERT INTO plot_nodes (book_id, layer, node_type, title, summary) VALUES (?,0,'plot','全书根','')",
            (book_id,),
        )
        l0_id = c.lastrowid
    else:
        l0_id = l0["id"]

    # L0-PH: 占位链入口
    l0_ph = await (await db.execute(
        "SELECT id FROM plot_nodes WHERE book_id=? AND layer=0 AND node_type='placeholder'", (book_id,)
    )).fetchone()
    if not l0_ph:
        c = await db.execute(
            "INSERT INTO plot_nodes (book_id, layer, node_type, title, summary, importance, parent_id) VALUES (?,0,'placeholder','','',1,?)",
            (book_id, l0_id),
        )
        l0_ph_id = c.lastrowid
    else:
        l0_ph_id = l0_ph["id"]

    # L0-SUM: "全文概括" (初期为空，merge 后填充)
    l0_sum = await (await db.execute(
        "SELECT id FROM plot_nodes WHERE book_id=? AND layer=0 AND node_type='summary'", (book_id,)
    )).fetchone()
    if not l0_sum:
        c = await db.execute(
            "INSERT INTO plot_nodes (book_id, layer, node_type, title, summary, importance, parent_id) VALUES (?,0,'summary','全文概括','',1,?)",
            (book_id, l0_id),
        )
        l0_sum_id = c.lastrowid
    else:
        l0_sum_id = l0_sum["id"]

    # L1-PH (挂在 L0-PH 下)
    l1 = await (await db.execute(
        "SELECT id FROM plot_nodes WHERE book_id=? AND layer=1 AND title='' AND parent_id=?", (book_id, l0_ph_id)
    )).fetchone()
    if not l1:
        c = await db.execute(
            "INSERT INTO plot_nodes (book_id, layer, node_type, title, summary, importance, parent_id) VALUES (?,1,'plot','','',1,?)",
            (book_id, l0_ph_id),
        )
        l1_id = c.lastrowid
    else:
        l1_id = l1["id"]

    # L2-PH (挂在 L1-PH 下)
    l2 = await (await db.execute(
        "SELECT id FROM plot_nodes WHERE book_id=? AND layer=2 AND title='' AND parent_id=?", (book_id, l1_id)
    )).fetchone()
    if not l2:
        c = await db.execute(
            "INSERT INTO plot_nodes (book_id, layer, node_type, title, summary, importance, parent_id) VALUES (?,2,'plot','','',1,?)",
            (book_id, l1_id),
        )
        l2_id = c.lastrowid
    else:
        l2_id = l2["id"]

    # L3-PH 一个 (挂在 L2-PH 下)，不分章节
    row = await (await db.execute(
        "SELECT id FROM plot_nodes WHERE book_id=? AND layer=3 AND title=? AND parent_id=?",
        (book_id, "", l2_id),
    )).fetchone()
    if row:
        l3_ph_id = row["id"]
    else:
        c = await db.execute(
            "INSERT INTO plot_nodes (book_id, layer, node_type, title, summary, importance, parent_id) VALUES (?,3,'plot',?,?,1,?)",
            (book_id, "", "待分组", l2_id),
        )
        l3_ph_id = c.lastrowid

    # 孤儿 L4 挂到 L3-PH
    await db.execute(
        "UPDATE plot_nodes SET parent_id=? WHERE book_id=? AND layer=4 AND parent_id IS NULL",
        (l3_ph_id, book_id),
    )

    await db.commit()

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
        tracker.push(book_id, {"type": "step_complete", "step": "parse"})
        return

    tracker.push(book_id, {"type": "step_start", "step": "parse",
               "label": "章节解析", "total": len(chapters_to_process)})
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
    tracker.push(book_id, {"type": "step_complete", "step": "parse",
               "chapters_count": len(chapters_to_process)})


async def _step_l4_per_chapter(db, book_id, parse_result, chapters_to_process, pipeline_tokens=None):
    """Step 2: 逐章 L4 语义分组+轻量概括。"""
    processed, skipped = 0, 0
    total_groups_estimate = 0
    total_tokens = {"in": 0, "out": 0}
    if pipeline_tokens is None:
        pipeline_tokens = total_tokens
    
    tracker.push(book_id, {"type": "step_start", "step": "l4",
               "label": "语义分组", "total": len(chapters_to_process)})

    for ch_idx in chapters_to_process:
        # ── 取消检查点 ──
        current_task_l4 = asyncio.current_task()
        if current_task_l4 and current_task_l4.cancelled():
            raise asyncio.CancelledError()

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
        if status in ("processing", "pending"):
            # 上次崩溃/取消导致残留，清理后重跑
            await _cleanup_layer(db, book_id, chapter_db_id, 4)
            print(f"  [INFO] Chapter {ch['index']} L4 was {status}, cleaning up and retrying")

        # 加载 atoms
        atoms = await _load_atoms_for_chapter(db, book_id, ch["index"])
        if not atoms:
            continue

        await _set_state(db, book_id, chapter_db_id, "l4", "processing")
        await db.commit()

        print(f"[INFO] L4: chapter {ch['index']}/{len(parse_result['chapters'])} ({len(atoms)} atoms)...")
        try:
            # 流式回调
            stream_buf = []
            async def on_l4_chunk(text: str):
                stream_buf.append(text)
                display = "".join(stream_buf)[-200:]
                tracker.push(book_id, {"type": "stream", "text": display})
                await db.execute(
                    "UPDATE plot_nodes SET summary=? WHERE book_id=? AND layer=1 AND title=''",
                    (f"正在分组: {display}", book_id),
                )
            async def on_l4_reasoning(text: str):
                tracker.push(book_id, {"type": "reasoning", "text": text})

            # ── 滑动窗口：~2000 字一窗，句子完整 ──
            WINDOW_CHARS = 2000
            windows: list[list[dict]] = []
            cur_win: list[dict] = []
            cur_chars = 0
            for a in atoms:
                a_chars = len(a["content"])
                if cur_chars + a_chars > WINDOW_CHARS and cur_win:
                    windows.append(cur_win)
                    cur_win = []
                    cur_chars = 0
                cur_win.append(a)
                cur_chars += a_chars
            if cur_win:
                windows.append(cur_win)

            # 最后窗口过小（<500 字）则合并到上一个窗口，省一次 API 调用
            MIN_LAST_WINDOW = 500
            if len(windows) >= 2:
                last_chars = sum(len(a["content"]) for a in windows[-1])
                if last_chars < MIN_LAST_WINDOW:
                    windows[-2].extend(windows[-1])
                    windows.pop()

            all_l4_groups: list[dict] = []
            all_genre_tags: list[str] = []
            carry_over_ids: list[int] = []
            window_count = len(windows)

            for win_idx, win_atoms in enumerate(windows):
                # ── 取消检查点 ──
                ct = asyncio.current_task()
                if ct and ct.cancelled():
                    raise asyncio.CancelledError()

                is_last = (win_idx == window_count - 1)
                # 合并上窗 carry_over atom dicts
                carry_atoms = [a for a in atoms if a["id"] in carry_over_ids] if carry_over_ids else []
                proc_atoms = carry_atoms + win_atoms
                wlabel = f"{win_idx+1}/{window_count}"

                l4_groups, genre_tags, tokens, carry_over_ids = await process_l4(
                    ch["index"], proc_atoms,
                    is_last_window=is_last, window_label=wlabel,
                    on_chunk=on_l4_chunk, on_reasoning=on_l4_reasoning,
                )

                total_tokens["in"] += tokens["in"]; total_tokens["out"] += tokens["out"]
                pipeline_tokens["in"] += tokens["in"]; pipeline_tokens["out"] += tokens["out"]
                tracker.push(book_id, {"type": "tokens", "in": total_tokens["in"], "out": total_tokens["out"]})

                # ── 即时写入本窗分组 + 刷新树 ──
                if l4_groups:
                    await _write_l4_incremental(db, book_id, l4_groups)
                    # 找父节点：优先 L3-PH，缺失则兜底 L2-PH
                    parent = await (await db.execute(
                        "SELECT id FROM plot_nodes WHERE book_id=? AND layer=3 AND title=?",
                        (book_id, ""),
                    )).fetchone()
                    if not parent:
                        parent = await (await db.execute(
                            "SELECT id FROM plot_nodes WHERE book_id=? AND layer=2 AND title=''",
                            (book_id,),
                        )).fetchone()
                    if parent:
                        await db.execute(
                            "UPDATE plot_nodes SET parent_id=? WHERE book_id=? AND layer=4 AND parent_id IS NULL",
                            (parent["id"], book_id),
                        )
                    await db.commit()
                    await push_l4_adds(db, book_id, l4_groups, tracker)

                all_l4_groups.extend(l4_groups)
                if genre_tags:
                    all_genre_tags.extend(genre_tags)

                print(f"  [INFO]   L4 win{wlabel}: {len(proc_atoms)} atoms → {len(l4_groups)} groups"
                      + (f", carry_over={carry_over_ids}" if carry_over_ids else ""))

            # 确保 carry_over 归组（最后窗口不应有，但兜底）
            if carry_over_ids:
                all_l4_groups.append({"atom_ids": sorted(carry_over_ids), "summary": "（跨窗衔接句）"})

            l4_groups = all_l4_groups
            # 首次保存 genre_tags
            if all_genre_tags:
                existing = await (await db.execute(
                    "SELECT genre_tags FROM books WHERE id=?", (book_id,)
                )).fetchone()
                if existing and (not existing["genre_tags"] or existing["genre_tags"] == "[]"):
                    await db.execute("UPDATE books SET genre_tags=? WHERE id=?",
                                     (json.dumps(all_genre_tags), book_id))
            await _set_state(db, book_id, chapter_db_id, "l4", "complete")
            await db.commit()
            processed += 1
            total_groups_estimate += len(l4_groups)
            print(f"  [INFO] Chapter {ch['index']} L4 done: {len(l4_groups)} groups")
            tracker.push(book_id, {"type": "progress", "step": "l4",
                         "current": processed, "total": len(chapters_to_process),
                         "chapter_index": ch["index"], "groups": len(l4_groups),
                         "chapter_title": ch.get("title", "")[:30]})
        except Exception as e:
            await _set_state(db, book_id, chapter_db_id, "l4", "failed", str(e))
            await db.commit()
            print(f"  [ERROR] Chapter {ch['index']} L4 failed: {e}")
            tracker.push(book_id, {"type": "error", "step": "l4", "message": str(e)[:200],
                         "chapter_index": ch["index"]})

    print(f"[INFO] L4 pass: {processed} processed, {skipped} skipped")
    tracker.push(book_id, {"type": "step_complete", "step": "l4",
               "chapters_processed": processed, "total_groups": total_groups_estimate})


async def _step_l3_per_chapter(db, book_id, parse_result, chapters_to_process, pipeline_tokens=None):
    """Step 3: 逐组 L3——每个 L4 句子组独立调用 AI，带全章上下文+前文 L3 概括。"""
    global_group_counter = 0  # 跨章累计
    total_tokens = {"in": 0, "out": 0}
    if pipeline_tokens is None:
        pipeline_tokens = total_tokens

    # 估算总组数（优先用 L4 已完成数量）
    total_groups_estimate = 0
    for ch_idx_est in chapters_to_process:
        ch_est = parse_result["chapters"][ch_idx_est - 1]
        ch_db_id = await _get_chapter_db_id(db, book_id, ch_est["index"])
        if ch_db_id and await _get_state(db, book_id, ch_db_id, "l4") in ("complete", "processing"):
            l4g = await _load_l4_groups_for_chapter(db, book_id, ch_est["index"])
            total_groups_estimate += len(l4g)
    if total_groups_estimate == 0:
        total_groups_estimate = len(chapters_to_process) * 20  # fallback 估算

    # Emit L3 step_start once (before chapter loop, not per-chapter)
    tracker.push(book_id, {"type": "step_start", "step": "l3",
                 "label": "场景聚合", "total_groups": total_groups_estimate})

    for ch_idx in chapters_to_process:
        ch = parse_result["chapters"][ch_idx - 1]
        chapter_db_id = await _get_chapter_db_id(db, book_id, ch["index"])
        if not chapter_db_id:
            continue

        status = await _get_state(db, book_id, chapter_db_id, "l3")
        if status == "complete":
            print(f"  [INFO] Chapter {ch['index']} L3 already complete, skip")
            continue
        if status == "failed":
            print(f"  [INFO] Chapter {ch['index']} L3 previously failed, skip (use retry)")
            continue
        if status in ("processing", "pending"):
            await _cleanup_layer(db, book_id, chapter_db_id, 3)
            print(f"  [INFO] Chapter {ch['index']} L3 was {status}, cleaning up and retrying from group 0")

        l4_groups = await _load_l4_groups_for_chapter(db, book_id, ch["index"])
        if not l4_groups:
            continue

        await _set_state(db, book_id, chapter_db_id, "l3", "processing")
        await db.commit()

        print(f"[INFO] L3: ch{ch['index']}/{len(parse_result['chapters'])} — {len(l4_groups)} L4 groups, API call per group...")
        prior_l3 = []

        try:
            for g_idx, group in enumerate(l4_groups):
                # ── 取消检查点 ──
                current_task = asyncio.current_task()
                if current_task and current_task.cancelled():
                    raise asyncio.CancelledError()

                global_group_counter += 1
                # 流式回调：推送 L3 思考过程
                stream_buf_l3 = []
                async def on_l3_chunk(text: str):
                    stream_buf_l3.append(text)
                    display = "".join(stream_buf_l3)[-200:]
                    tracker.push(book_id, {"type": "stream", "text": display})
                    await db.execute(
                        "UPDATE plot_nodes SET summary=? WHERE book_id=? AND layer=1 AND title=''",
                        (f"场景聚合: {display}", book_id),
                    )
                async def on_l3_reasoning(text: str):
                    tracker.push(book_id, {"type": "reasoning", "text": text})

                result = await process_single_l3(g_idx, group, l4_groups, prior_l3,
                                                  on_chunk=on_l3_chunk, on_reasoning=on_l3_reasoning)

                if result.get("is_new"):
                    scene_data = [{
                        "parent_l4_indices": [g_idx],
                        "title": result.get("title", ""),
                        "summary": result.get("summary", ""),
                        "importance": result.get("importance", 5),
                        "story_time_label": result.get("story_time_label", ""),
                    }]
                    l3_ids = await _write_l3_incremental(db, book_id, l4_groups, scene_data)
                    prior_l3.append({**scene_data[0], "parent_l4_indices": [g_idx], "_db_id": l3_ids.get(0)})
                elif prior_l3:
                    prior_l3[-1]["summary"] = result.get("summary", prior_l3[-1]["summary"])
                    prior_l3[-1]["title"] = result.get("title", prior_l3[-1]["title"])
                    prior_l3[-1]["parent_l4_indices"].append(g_idx)
                    # 延续场景：将当前 L4 组也链接到该 L3
                    l3_db_id = prior_l3[-1].get("_db_id")
                    if l3_db_id:
                        await _link_l4_to_l3(db, book_id, l4_groups, [g_idx], l3_db_id)
                else:
                    scene_data = [{"parent_l4_indices": [g_idx], "title": result.get("title", ""),
                                   "summary": result.get("summary", ""), "importance": result.get("importance", 5),
                                   "story_time_label": result.get("story_time_label", "")}]
                    l3_ids = await _write_l3_incremental(db, book_id, l4_groups, scene_data)
                    prior_l3.append({**scene_data[0], "parent_l4_indices": [g_idx], "_db_id": l3_ids.get(0)})

                print(f"  [INFO]   g{g_idx+1}/{len(l4_groups)} {'+' if result.get('is_new') else '~'} "
                      f"\"{result.get('title','')[:30]}\"")
                tok = result.get("_tokens", {})
                total_tokens["in"] += tok.get("in", 0); total_tokens["out"] += tok.get("out", 0)
                pipeline_tokens["in"] += tok.get("in", 0); pipeline_tokens["out"] += tok.get("out", 0)
                # 逐组提交 + 增量事件
                # 新场景 → node_add L3；迁移 L4 → node_delete
                if result.get("is_new") and l3_ids:
                    await push_l3_add(db, book_id, scene_data[0], l3_ids.get(0), tracker)
                await push_l4_deletes(db, book_id, l4_groups, [g_idx], tracker)
                await db.commit()
                tracker.push(book_id, {"type": "tree_refresh"})
                tracker.push(book_id, {"type": "l3_progress", "step": "l3",
                             "current": global_group_counter, "total": total_groups_estimate,
                             "scene_title": result.get("title", ""),
                             "is_new": result.get("is_new", False),
                             "tokens_in": total_tokens["in"], "tokens_out": total_tokens["out"]})

            await _set_state(db, book_id, chapter_db_id, "l3", "complete")
            await db.commit()
            tracker.push(book_id, {"type": "tree_refresh"})
            print(f"  [INFO] Chapter {ch['index']} L3 done: {len(prior_l3)} scenes from {len(l4_groups)} groups")
            tracker.push(book_id, {"type": "progress", "step": "l3",
                         "chapter_done": ch["index"], "scenes": len(prior_l3),
                         "chapter_title": ch.get("title", "")[:30]})
        except Exception as e:
            await _set_state(db, book_id, chapter_db_id, "l3", "failed", str(e))
            await db.commit()
            print(f"  [ERROR] Chapter {ch['index']} L3 failed at group {g_idx if 'g_idx' in dir() else '?'}: {e}")
            tracker.push(book_id, {"type": "error", "step": "l3", "message": str(e)[:200],
                         "chapter_index": ch["index"]})

    tracker.push(book_id, {"type": "step_complete", "step": "l3",
               "total_groups_done": global_group_counter})


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
    if status in ("processing", "pending", "failed"):
        await _cleanup_layer(db, book_id, 0, 2)
        print(f"[INFO] L2 global was {status}, cleaning up and retrying")

    all_l3 = await _load_all_l3_scenes(db, book_id)
    if not all_l3:
        print("[WARN] No L3 scenes found, skip L2")
        return

    await _set_state(db, book_id, 0, "l2_global", "processing")
    await db.commit()

    tracker.push(book_id, {"type": "step_start", "step": "l2_global",
               "label": "跨章聚合"})
    print(f"[INFO] L2 global: aggregating {len(all_l3)} L3 scenes across all chapters...")
    try:
        l2_events = await process_l2(all_l3)
        if l2_events:
            await _write_l2_global(db, book_id, all_l3, l2_events)
        await _set_state(db, book_id, 0, "l2_global", "complete")
        await db.commit()
        tracker.push(book_id, {"type": "tree_refresh"})
        print(f"[INFO] L2 global done: {len(l2_events)} events")
        tracker.push(book_id, {"type": "step_complete", "step": "l2_global",
                     "events_count": len(l2_events)})
    except Exception as e:
        await _set_state(db, book_id, 0, "l2_global", "failed", str(e))
        await db.commit()
        print(f"[ERROR] L2 global failed: {e}")
        tracker.push(book_id, {"type": "error", "step": "l2_global", "message": str(e)[:200]})
        await db.commit()


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
    tracker.push(book_id, {"type": "step_start", "step": "l1_merge",
               "label": "宏观叙事"})
    print(f"[INFO] Merge Agent: aggregating {len(l2_nodes)} L2 nodes...")

    from agents.merge_agent import MergeAgent
    merge = MergeAgent()
    try:
        merge_result = await merge.aggregate(book_id, l2_nodes)

        # 获取 L0 根节点（L1 事件的父）
        l0_root = await (await db.execute(
            "SELECT id FROM plot_nodes WHERE book_id=? AND layer=0 AND parent_id IS NULL", (book_id,)
        )).fetchone()
        l0_root_id = l0_root["id"] if l0_root else None

        for l1 in merge_result.get("layer_1_events", []):
            cursor = await db.execute(
                """INSERT INTO plot_nodes (book_id, layer, node_type, title, summary, detail, importance, st_label, parent_id)
                   VALUES (?, 1, 'plot', ?, ?, ?, ?, ?, ?)""",
                (book_id, l1.get("title", ""), l1.get("summary", ""), "",
                 l1.get("importance", 7), l1.get("story_time_label", ""), l0_root_id),
            )
            l1_id = cursor.lastrowid
            for l2_id in l1.get("parent_l2_ids", []):
                await db.execute("UPDATE plot_nodes SET parent_id=? WHERE id=?", (l1_id, l2_id))

        ns = merge_result.get("narrative_summary", "")
        if ns:
            await db.execute("UPDATE books SET narrative_summary=? WHERE id=?", (ns, book_id))
            # 填充 L0-SUM "全文概括" 节点
            await db.execute(
                "UPDATE plot_nodes SET summary=? WHERE book_id=? AND layer=0 AND node_type='summary'",
                (ns, book_id),
            )

        await _set_state(db, book_id, 0, "l1_merge", "complete")
        await db.commit()
        tracker.push(book_id, {"type": "tree_refresh"})
        print(f"[INFO] Merge done: {len(merge_result.get('layer_1_events', []))} L1 events")
        tracker.push(book_id, {"type": "step_complete", "step": "l1_merge",
                     "events_count": len(merge_result.get('layer_1_events', []))})
    except Exception as e:
        await _set_state(db, book_id, 0, "l1_merge", "failed", str(e))
        await db.commit()
        print(f"[ERROR] Merge failed: {e}")
        tracker.push(book_id, {"type": "error", "step": "l1_merge", "message": str(e)[:200]})


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
    # 查找 L2 占位作为父节点
    c = await db.execute(
        "SELECT id FROM plot_nodes WHERE book_id=? AND layer=2 AND title='' LIMIT 1", (book_id,)
    )
    l2_ph = await c.fetchone()
    parent_id = l2_ph["id"] if l2_ph else None

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
            """INSERT INTO plot_nodes (book_id, layer, node_type, title, summary, importance, st_label, parent_id)
               VALUES (?, 3, 'plot', ?, ?, ?, ?, ?)""",
            (book_id, scene.get("title", ""), scene.get("summary", ""),
             scene.get("importance", 5), scene.get("story_time_label", ""), parent_id),
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

    return l3_db_ids


async def _link_l4_to_l3(db, book_id, l4_groups, l4_indices: list[int], l3_db_id: int):
    """将指定 L4 索引对应的 DB 节点重新链接到某个 L3 节点。"""
    all_aids = [aid for idx in l4_indices if idx < len(l4_groups)
                for aid in l4_groups[idx].get("atom_ids", [])]
    if not all_aids:
        return
    placeholders = ",".join("?" * len(all_aids))
    cursor = await db.execute(
        f"SELECT id, plot_node_id FROM atoms WHERE id IN ({placeholders})", all_aids,
    )
    done = set()
    for r in await cursor.fetchall():
        l4_id = r["plot_node_id"]
        if l4_id and l4_id not in done:
            done.add(l4_id)
            await db.execute("UPDATE plot_nodes SET parent_id=? WHERE id=?", (l3_db_id, l4_id))


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
    if not rows:
        return []

    # 批量获取所有 L4 的 atom_ids（避免 N+1）
    l4_ids = [r["id"] for r in rows]
    placeholders = ",".join("?" * len(l4_ids))
    cursor2 = await db.execute(
        f"SELECT id, plot_node_id FROM atoms WHERE plot_node_id IN ({placeholders}) ORDER BY reading_order",
        l4_ids,
    )
    l4_to_atoms: dict[int, list[int]] = {lid: [] for lid in l4_ids}
    for a in await cursor2.fetchall():
        pid = a["plot_node_id"]
        if pid in l4_to_atoms:
            l4_to_atoms[pid].append(a["id"])

    return [
        {
            "group_index": i,
            "summary": r["summary"] or "",
            "atom_ids": l4_to_atoms.get(r["id"], []),
        }
        for i, r in enumerate(rows)
    ]


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
