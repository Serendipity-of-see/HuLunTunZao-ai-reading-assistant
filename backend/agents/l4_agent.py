"""L4 Agent — 句子语义分组 + 轻量概括（滑动窗口）。模型: flash, T=0.3, 8192 tokens。"""

from agents._base import llm_call_stream

L4_PROMPT = """你是小说句子分析专家。将原文句子按事理分组，并做最轻量概括。

输入格式：atom 列表 [{id, content}]

**滑动窗口说明**：整章文本太长，被分成多个窗口依次处理。
- 如果末尾 1-3 句与后文（不在本窗口内）有紧密关联，无法形成完整语义组，
  把它们的 atom_ids 放入 carry_over_atom_ids，留给下个窗口处理。
- 不要把明显可以独立成组的句子标记为 carry_over。
- 最后窗口：必须处理全部句子，carry_over 必须为空。

输出纯 JSON：
{"layer_4_groups":[{"atom_ids":[1,2,3],"summary":"轻量概括"}], "carry_over_atom_ids":[]}

分组规则：
- 同一事理/同一画面/同一动作/同一话题的连续句子归为一组，**每组控制在 2-4 句**
- **以下情况必须切开新组**：
  1. 时间发生明显跳跃（如"睡了两小时""第二天"）→ 切
  2. 空间/地点明显转换（如从树下到水边、梦境到现实）→ 切
  3. 话题或动作有明显转折（如从描写转入对话、从叙述转入回忆）→ 切
- 分组按原文句子顺序排列，不得打乱顺序
- 过渡描写（与后文无联系且不塑造人物）→ 单列一组

**概括规则（关键——保留原文阅读体验）：**
- 删减约1/3篇幅，保留约2/3（原文10句→概括6-7句的量）。不是重写，是缩句
- **人称视角必须保留**：原文"我"不能变"他/讲述者"，第一人称必须保持第一人称
- **所有出现的事物、人物、动作都要保留**，不能省略任何实体
- 比喻和描写可概括为修饰结果
- 对话保留关键对白内容和说话人
- 保持原文叙事节奏——读完概括应有类似的阅读体验
- 已归组的 atom 必须全覆盖，不得遗漏；carry_over 的除外"""


async def process_l4(chapter_index: int, atoms: list[dict],
                     is_last_window: bool = True,
                     window_label: str = "",
                     on_chunk=None, on_reasoning=None) -> tuple[list[dict], list[str], dict]:
    """滑动窗口 L4 分组。返回 (l4_groups, genre_tags, tokens, carry_over_ids)。"""
    if not atoms:
        return [], [], {"in": 0, "out": 0}, []

    atoms_text = "\n".join(f"[{a['id']}] {a['content']}" for a in atoms)
    window_hint = f"窗口{window_label}（共{len(atoms)}句）" if window_label else f"共{len(atoms)}句"
    last_hint = "这是最后一个窗口，必须处理全部句子，carry_over_atom_ids 必须为空。" if is_last_window else \
                "末尾若有跨窗口关联的句子，放入 carry_over_atom_ids，不要强行归组。"

    user_msg = f"第{chapter_index}章 {window_hint}。{last_hint}\n\n{atoms_text}"

    label_suffix = f"-{window_label}" if window_label else ""
    result = await llm_call_stream(
        "deepseek-v4-flash", L4_PROMPT, user_msg,
        label=f"L4-ch{chapter_index}{label_suffix}", temperature=0.3, max_tokens=8192,
        reasoning_effort=None,
        on_chunk=on_chunk, on_reasoning=on_reasoning,
    )
    l4_groups = result.get("layer_4_groups", [])
    carry_over = result.get("carry_over_atom_ids", [])
    if not l4_groups and not carry_over:
        return [], [], result.get("_tokens", {"in": 0, "out": 0}), []

    # 过滤 carry_over：那些 atom 不参与本窗口分组
    carry_set = set(carry_over)
    for g in l4_groups:
        g["atom_ids"] = [aid for aid in g.get("atom_ids", []) if aid not in carry_set]

    # 完整性检查
    covered = set()
    for g in l4_groups:
        for aid in g.get("atom_ids", []):
            covered.add(aid)
    all_ids = {a["id"] for a in atoms}
    missing = all_ids - covered - carry_set
    if missing:
        print(f"  [L4] WARNING: {len(missing)} atoms not covered, adding fallback group")
        l4_groups.append({"atom_ids": sorted(missing), "summary": "（未分组句）"})

    # 只保留有效 atom_ids 的组
    l4_groups = [g for g in l4_groups if g.get("atom_ids")]
    l4_groups.sort(key=lambda g: min(g["atom_ids"]) if g.get("atom_ids") else float("inf"))
    return l4_groups, result.get("genre_tags", []), result.get("_tokens", {"in": 0, "out": 0}), carry_over
