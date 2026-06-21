"""L2 Agent — 跨章事件聚合。模型: pro, T=0.2, 4096 tokens。"""

from agents._base import llm_call

L2_PROMPT = """你是跨章情节整合专家。基于全书所有 L3 场景，构建 L2 小事件。

输入：全书 L3 场景列表 [{global_index, chapter_index, title, summary, importance}]
输出纯 JSON：
{"layer_2_events":[{"parent_l3_indices":[0,5,12],"title":"事件标题","summary":"此事件从始至终的连贯叙事概括","importance":7,"story_time_label":"第1-3章","cross_refs":[]}]}

构建逻辑：
- 一个 L2 事件 = 一个完整的叙事节奏单位（一次战斗/一场考核/一回论辩）
- 跨章聚合：同一事件的 L3 场景可能分散在不同章节
- **以下情况必须切开不同的 L2（硬性规则）**：
  1. 叙事核心主体发生根本转变（如前面的故事围绕叙述者自己的经历，后面围绕另一个人物的独立人生）→ 切
  2. 故事层级切换（外层框架→嵌套故事，两段叙事没有因果/主题关联）→ 切
- **不应切分的情况**：对话中的人称切换、同一事件内的视角微调——这些是微观结构，不影响 L2 聚合
- importance: 9-10核心主线事件/7-8重要事件/4-6普通/1-3支线

覆盖全部 L3 场景，每个 L3 必须归属到某个 L2。"""


async def process_l2(all_l3: list[dict]) -> list[dict]:
    """全书 L3 → L2 事件。"""
    if not all_l3:
        return []
    l3_text = "\n".join(
        f"[{s['global_index']}] ch={s.get('chapter_index','?')} "
        f"imp={s.get('importance',5)} {s.get('title','')}: {s.get('summary','')[:100]}"
        for s in all_l3
    )
    result = await llm_call(
        "deepseek-v4-flash", L2_PROMPT,
        f"全书 L3 场景（共{len(all_l3)}个）：\n\n{l3_text}",
        label="L2-global", temperature=0.2, max_tokens=4096,
    )
    return result.get("layer_2_events", [])
