import json
import time
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from config import get_api_key, DEEPSEEK_BASE_URL, DEEPSEEK_PRO_MODEL

MERGE_PROMPT = """你是跨章节情节整合专家。将分散的 L2 小事件聚合为 L1 完整事件始末。

输入：已生成的 L2 小事件列表（id, title, summary, importance）
输出：纯 JSON，格式：
{
  "layer_1_events": [
    {
      "parent_l2_ids": [L2的id, ...],
      "title": "完整事件标题（不剧透）",
      "summary": "此事件从始至终的连贯叙事概括（3-5句）",
      "importance": 8,
      "story_time_label": "如'第一难'或'某人登场至退场'"
    }
  ],
  "narrative_summary": "全书连贯叙事概括，可独立阅读，200-500字"
}

聚合标准：
- 一个 L1 = 一个完整故事弧（起→承→转→合）
- 小文件可能只有 1 个 L1，大文件按叙事转折切分
- 每个 L2 必须归属到某个 L1
- 标题不剧透不暗示结局
- importance: 9-10核心主线, 7-8重要"""


class MergeAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=DEEPSEEK_PRO_MODEL,
            api_key=get_api_key(),
            base_url=DEEPSEEK_BASE_URL,
            temperature=0.4,
            max_tokens=4096,
        )

    async def aggregate(self, book_id: int, l2_nodes: list[dict]) -> dict:
        """聚合 L2→L1，生成 narrative_summary。"""
        if len(l2_nodes) <= 1:
            # 只有一个 L2，自动生成一个 L1 包裹它
            l2 = l2_nodes[0]
            return {
                "layer_1_events": [{
                    "parent_l2_ids": [l2["id"]],
                    "title": l2.get("title", "全文")[:20],
                    "summary": l2.get("summary", ""),
                    "importance": l2.get("importance", 7),
                    "story_time_label": "全文",
                }],
                "narrative_summary": l2.get("summary", ""),
            }

        # 构建 L2 摘要列表
        l2_text = "\n".join(
            f'[{n["id"]}] imp={n.get("importance",5)} {n.get("title","")}: {n.get("summary","")[:100]}'
            for n in l2_nodes
        )

        messages = [
            SystemMessage(content=MERGE_PROMPT),
            HumanMessage(content=f"L2 小事件列表（共{len(l2_nodes)}个）：\n\n{l2_text}"),
        ]

        t0 = time.time()
        response = await self.llm.ainvoke(messages)
        elapsed = time.time() - t0
        content = response.content.strip()
        if content.startswith("```"):
            content = "\n".join(content.split("\n")[1:-1])

        # 容错：尝试多种方式提取 JSON
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(content[start:end])
            else:
                raise RuntimeError(f"Merge Agent JSON 解析失败: {content[:500]}")

        print(f"  [Merge Agent] {len(l2_nodes)} L2s -> {len(result.get('layer_1_events',[]))} L1s, {elapsed:.1f}s")
        return result
