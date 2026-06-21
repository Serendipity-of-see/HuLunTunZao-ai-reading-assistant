"""L3 Agent — 逐组场景聚合。模型: flash, T=0.3, 4096 tokens。使用流式 LLM 产生实时反馈。"""

from agents._base import llm_call_stream

L3_PROMPT = """你是小说情节分析专家。逐组将每个 L4 句子组归入一个场景。

你会被逐组调用——每次处理一个 L4 句子组，同时你已知全文上下文和前文已生成的所有场景块。

输入：
- current_group: 当前要处理的 L4 句子组
- all_groups: 本章所有 L4 句子组（上下文）
- prior_l3: 前文已概括的 L3 场景块列表

任务：
1. 判断当前句子组是延续前一个场景，还是开启一个新场景
2. 如果延续：输出当前场景的更新后概括
3. 如果开启新场景：输出新场景的概括

输出纯 JSON：
{"scene_index": 0, "is_new": false, "title": "场景标题", "summary": "此场景更新后的完整概括（2-3句）",
 "importance": 5, "story_time_label": "如'酒馆夜晚'", "parent_l4_indices": [当前组索引]}

场景切换标准：空间/地点变换、时间跳跃、话题/事件明显转换
importance: 9-10核心场景/7-8重要场景/4-6普通/1-3过渡"""


async def process_single_l3(group_idx: int, group: dict,
                             all_groups: list[dict], prior_l3: list[dict],
                             on_chunk=None, on_reasoning=None) -> dict:
    """逐组 L3：每次处理一个 L4 组，传全章上下文 + 前文 L3。支持流式回调。"""
    group_text = f"[{group_idx}] {group.get('summary', '')[:120]}"
    all_text = "\n".join(f"[{i}] {g.get('summary', '')[:100]}" for i, g in enumerate(all_groups))
    prior_text = "\n".join(
        f"场景{i}: {s.get('title','')}: {s.get('summary','')[:120]}" for i, s in enumerate(prior_l3)
    ) if prior_l3 else "（尚无前文场景）"

    user_msg = (
        f"当前组: {group_text}\n\n"
        f"全文上下文:\n{all_text}\n\n"
        f"前文已概括的场景:\n{prior_text}"
    )

    result = await llm_call_stream(
        "deepseek-v4-flash", L3_PROMPT, user_msg,
        label=f"L3-g{group_idx}", temperature=0.3, max_tokens=4096,
        reasoning_effort=None,
        on_chunk=on_chunk, on_reasoning=on_reasoning,
    )
    result["parent_l4_indices"] = result.get("parent_l4_indices", [group_idx])
    return result
