import json
import time
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from config import get_api_key, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

L4_PROMPT = """你是小说句子分析专家。将原文句子按事理分组，并做最轻量概括。

输入：atom 列表 [{id, content}]
输出纯 JSON：
{"layer_4_groups":[{"atom_ids":[1,2,3],"summary":"轻量概括"}]}

分组规则：
- 同一事理/同一画面/同一动作/同一话题的连续句子归为一组（3-8句）
- 分组按原文句子顺序排列，不得打乱顺序
- 过渡描写（与后文无联系且不塑造人物）→ 单列一组

**概括规则（关键——保留原文阅读体验）：**
- 删减约1/3篇幅，保留约2/3（原文10句→概括6-7句的量）。不是重写，是缩句
- **人称视角必须保留**：原文"我"不能变"他/讲述者"，第一人称必须保持第一人称
- **所有出现的事物、人物、动作都要保留**，不能省略任何实体
- 比喻和描写可概括为修饰结果（如"脸涨得通红像熟透的柿子"→"脸涨得通红"）
- 对话保留关键对白内容和说话人
- 保持原文叙事节奏——读完概括应有类似的阅读体验
- 覆盖全部输入句子，每个 atom 必须属于某个组，不得遗漏"""

L3_ONLY_PROMPT = """你是小说情节分析专家。基于句子组摘要，构建场景块。

输入：L4 句子组列表 [{group_index, summary}]
输出纯 JSON：
{"genre_tags":[],"layer_3_scenes":[{"parent_l4_indices":[0,1],"title":"场景标题","summary":"场景概括（2-3句）","importance":5,"story_time_label":"如'酒馆夜晚'"}]}

构建逻辑：
- 将同一空间/时间/话题的 L4 组合并为一个场景
- 场景概括在 L4 基础上进一步压缩（2-3句），保留关键情节和转折
- importance: 9-10核心场景/7-8重要场景/4-6普通/1-3过渡
- genre_tags：从["悬疑","情感","战争","历史","武侠","玄幻","科幻","都市","青春","冒险","推理","恐怖"]中选1-3个

覆盖全部 L4 组，不得遗漏。"""

L2_GLOBAL_PROMPT = """你是跨章情节整合专家。基于全书所有 L3 场景，构建 L2 小事件。

输入：全书 L3 场景列表 [{global_index, chapter_index, title, summary, importance}]
输出纯 JSON：
{"layer_2_events":[{"parent_l3_indices":[0,5,12],"title":"事件标题","summary":"此事件从始至终的连贯叙事概括","importance":7,"story_time_label":"第1-3章","cross_refs":[]}]}

构建逻辑：
- 一个 L2 事件 = 一个完整的叙事节奏单位（一次战斗/一场考核/一回论辩）
- 跨章聚合：同一事件的 L3 场景可能分散在不同章节，将它们归入同一个 L2
- 事件边界通常对应叙事的加速（概括过渡）或减速（详细描写）转换点
- importance: 9-10核心主线事件/7-8重要事件/4-6普通/1-3支线
- story_time_label：标注事件跨越的章节范围，如"第1-3章"或"第5章中段至第6章初"

覆盖全部 L3 场景，每个 L3 必须归属到某个 L2。"""


class PlotAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=DEEPSEEK_MODEL, api_key=get_api_key(),
            base_url=DEEPSEEK_BASE_URL, temperature=0.3, max_tokens=8192,
        )

    # ── 旧接口（兼容 wrapper）──────────────────────────────────────────
    async def process_chapter(self, book_id: int, chapter_index: int,
                               atoms: list[dict]) -> dict:
        """[兼容] 两步处理：L4 → L3+L2。新代码请用拆分后的三个方法。"""
        if not atoms:
            return {"layer_4_groups": [], "layer_3_scenes": [], "layer_2_events": []}

        l4_groups, _ = await self.process_chapter_l4(chapter_index, atoms)
        if not l4_groups:
            return {"layer_4_groups": [], "layer_3_scenes": [], "layer_2_events": []}

        # 旧行为：L3+L2 一起出
        l4_text = "\n".join(
            f"[{i}] {g.get('summary', '')[:120]}"
            for i, g in enumerate(l4_groups)
        )
        result = await self._call(
            "L3+L2(legacy)",
            L3_L2_PROMPT_LEGACY,
            f"第{chapter_index}章 L4 句子组（共{len(l4_groups)}组）：\n\n{l4_text}",
            len(l4_groups),
        )
        return {
            "layer_4_groups": l4_groups,
            "layer_3_scenes": result.get("layer_3_scenes", []),
            "layer_2_events": result.get("layer_2_events", []),
            "genre_tags": result.get("genre_tags", []),
        }

    # ── 新接口：三层独立调用 ──────────────────────────────────────────

    async def process_chapter_l4(self, chapter_index: int, atoms: list[dict]) -> tuple[list[dict], list[str]]:
        """第1次调用：atoms → L4 语义分组 + 轻量概括。
        返回 (l4_groups, genre_tags)。"""
        if not atoms:
            return [], []

        atoms_text = "\n".join(f"[{a['id']}] {a['content']}" for a in atoms)
        result = await self._call(
            "L4",
            L4_PROMPT,
            f"第{chapter_index}章（共{len(atoms)}句），请全部处理，输出每个 atom 对应的 L4 分组和概括：\n\n{atoms_text}",
            len(atoms),
        )
        l4_groups = result.get("layer_4_groups", [])

        if not l4_groups:
            return [], []

        # 验证 atom 覆盖率
        covered = set()
        for g in l4_groups:
            for aid in g.get("atom_ids", []):
                covered.add(aid)
        all_ids = {a["id"] for a in atoms}
        missing = all_ids - covered
        extra = covered - all_ids
        if missing:
            print(f"  [Plot Agent] WARNING: {len(missing)} atoms not covered by L4, adding fallback group")
            l4_groups.append({"atom_ids": sorted(missing), "summary": "（未分组句）"})
        if extra:
            for g in l4_groups:
                g["atom_ids"] = [aid for aid in g.get("atom_ids", []) if aid in all_ids]

        # 按最小 atom_id 排顺序
        l4_groups.sort(key=lambda g: min(g["atom_ids"]) if g.get("atom_ids") else float("inf"))

        return l4_groups, result.get("genre_tags", [])

    async def process_chapter_l3(self, chapter_index: int, l4_groups: list[dict]) -> list[dict]:
        """第2次调用：L4 摘要 → L3 场景（逐章）。返回 layer_3_scenes。"""
        if not l4_groups:
            return []

        l4_text = "\n".join(
            f"[{i}] {g.get('summary', '')[:120]}"
            for i, g in enumerate(l4_groups)
        )
        result = await self._call(
            "L3",
            L3_ONLY_PROMPT,
            f"第{chapter_index}章 L4 句子组（共{len(l4_groups)}组）：\n\n{l4_text}",
            len(l4_groups),
        )
        return result.get("layer_3_scenes", [])

    async def process_l2_global(self, all_l3: list[dict]) -> list[dict]:
        """第3次调用：全书 L3 → L2 事件（全局）。all_l3 每项含 {global_index, chapter_index, title, summary, importance}。
        返回 layer_2_events，其中 parent_l3_indices 引用 global_index。"""
        if not all_l3:
            return []

        l3_text = "\n".join(
            f"[{s['global_index']}] ch={s.get('chapter_index','?')} imp={s.get('importance',5)} {s.get('title','')}: {s.get('summary','')[:100]}"
            for s in all_l3
        )
        result = await self._call(
            "L2-global",
            L2_GLOBAL_PROMPT,
            f"全书 L3 场景（共{len(all_l3)}个）：\n\n{l3_text}",
            len(all_l3),
        )
        return result.get("layer_2_events", [])

    # ── 内部 ──────────────────────────────────────────────────────────

    async def _call(self, label: str, system_prompt: str, user_msg: str, item_count: int) -> dict:
        t0 = time.time()
        response = await self.llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_msg),
        ])
        elapsed = time.time() - t0
        content = response.content.strip()
        if content.startswith("```"):
            content = "\n".join(content.split("\n")[1:-1])
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(content[start:end])
            else:
                raise RuntimeError(f"Plot Agent JSON 解析失败: {content[:500]}")
        print(f"  [Plot Agent] {label}: {item_count} items, {elapsed:.1f}s")
        return result


# 保留旧 prompt 供 process_chapter wrapper 使用
L3_L2_PROMPT_LEGACY = """你是小说情节分析专家。基于句子组摘要，构建场景和小事件。

输入：L4 句子组列表 [{group_index, summary}]
输出纯 JSON：
{"genre_tags":[],"layer_3_scenes":[{"parent_l4_indices":[0,1],"title":"场景标题","summary":"场景概括","importance":5,"story_time_label":"如'酒馆夜晚'"}],"layer_2_events":[{"parent_l3_indices":[0,1],"title":"事件标题","summary":"事件概括","importance":7,"story_time_label":"第一章","cross_refs":[]}]}

构建逻辑：
Step 1 — L3 场景块：
  将同一空间/时间/话题的 L4 组合并为一个场景。
  场景概括在 L4 基础上进一步压缩（2-3句），保留关键情节和转折。
  importance: 9-10核心场景/7-8重要场景/4-6普通/1-3过渡

Step 2 — L2 小事件：
  将 L3 按剧情缓急聚合。一个 L2 = 一个叙事节奏单位（一次战斗/一场考核/一回论辩）。
  事件概括为连贯叙事，保留起因→经过→结果。
  importance: 9-10核心主线事件/7-8重要事件/4-6普通/1-3支线

genre_tags：从["悬疑","情感","战争","历史","武侠","玄幻","科幻","都市","青春","冒险","推理","恐怖"]中选1-3个。

覆盖全部 L4 组，不得遗漏。"""
