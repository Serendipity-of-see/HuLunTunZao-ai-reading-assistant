"""共享 LLM 调用工具 — JSON 解析 + 独立日志文件 + 流式输出 + DeepSeek Thinking。"""

import asyncio
import json
import time
import traceback
from datetime import datetime
from openai import AsyncOpenAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from config import get_api_key, DEEPSEEK_BASE_URL, DATA_DIR

LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
INDEX_FILE = LOG_DIR / "_index.txt"  # 快速索引


def _index(label: str, msg: str):
    """追加一行到索引文件。"""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(INDEX_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{label}] {msg}\n")
    except Exception:
        pass


def _write_log(label: str, system_prompt: str, user_msg: str,
               response_text: str, reasoning_text: str,
               elapsed: float, tokens_in: int, tokens_out: int,
               error: str | None = None, parse_error_detail: str | None = None):
    """写入完整调用日志到独立文件。"""
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
        log_path = LOG_DIR / f"{safe_label}_{ts}.log"

        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"{'='*60}\n")
            f.write(f"Label:       {label}\n")
            f.write(f"Timestamp:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Duration:    {elapsed:.1f}s\n")
            f.write(f"Tokens:      in={tokens_in} out={tokens_out}\n")
            f.write(f"Reasoning:   {len(reasoning_text)} chars\n")
            f.write(f"Response:    {len(response_text)} chars\n")
            f.write(f"{'='*60}\n\n")

            f.write(f"── SYSTEM ({len(system_prompt)} chars) ──\n")
            f.write(system_prompt)
            f.write(f"\n\n── USER ({len(user_msg)} chars) ──\n")
            f.write(user_msg)

            if reasoning_text:
                f.write(f"\n\n── REASONING ({len(reasoning_text)} chars) ──\n")
                f.write(reasoning_text)

            f.write(f"\n\n── RESPONSE ({len(response_text)} chars) ──\n")
            f.write(response_text or "(empty)")

            if parse_error_detail:
                f.write(f"\n\n── PARSE ERROR ──\n")
                f.write(parse_error_detail)

            if error:
                f.write(f"\n\n── ERROR ──\n")
                f.write(error)

            f.write(f"\n\n── END ──\n")
    except Exception:
        pass  # 日志写入失败不应影响主流程


async def llm_call(
    model: str,
    system_prompt: str,
    user_msg: str,
    *,
    label: str = "LLM",
    temperature: float = 0.3,
    max_tokens: int = 8192,
) -> dict:
    """调用 LLM（阻塞），解析 JSON 响应，返回 dict（含 _tokens 字段）。"""
    _index(label, f"model={model} T={temperature} max_tok={max_tokens}")

    llm = ChatOpenAI(
        model=model, api_key=get_api_key(),
        base_url=DEEPSEEK_BASE_URL,
        temperature=temperature, max_tokens=max_tokens,
        request_timeout=300,
        model_kwargs={
            "extra_body": {"thinking": {"type": "disabled"}},
        },
    )
    t0 = time.time()
    error_msg = None
    try:
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_msg),
        ])
    except Exception as e:
        elapsed = time.time() - t0
        error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        _index(label, f"FAIL {elapsed:.1f}s {e}")
        _write_log(label, system_prompt, user_msg, "", "", elapsed, 0, 0, error=error_msg)
        raise

    elapsed = time.time() - t0
    content = response.content.strip()
    reasoning = response.additional_kwargs.get("reasoning_content", "") if hasattr(response, 'additional_kwargs') else ""

    token_usage = response.response_metadata.get("token_usage", {})
    if not token_usage:
        token_usage = response.usage_metadata or {}
    tokens_in = token_usage.get("prompt_tokens", token_usage.get("input_tokens", 0))
    tokens_out = token_usage.get("completion_tokens", token_usage.get("output_tokens", 0))

    _index(label, f"{elapsed:.1f}s {tokens_in}+{tokens_out} tokens")

    # JSON 解析
    if content.startswith("```"):
        content = "\n".join(content.split("\n")[1:-1])
    parse_err = None
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                result = json.loads(content[start:end])
            except json.JSONDecodeError as e2:
                parse_err = f"正向提取失败: {e2}\ncontent[:500]={content[:500]}"
                raise RuntimeError(f"{label} JSON 解析失败: {content[:500]}")
        else:
            parse_err = f"未找到 {{ }} 边界\ncontent[:500]={content[:500]}"
            raise RuntimeError(f"{label} JSON 解析失败: {content[:500]}")

    _write_log(label, system_prompt, user_msg, content, reasoning,
               elapsed, tokens_in, tokens_out, parse_error_detail=parse_err)
    print(f"  [{label}] {elapsed:.1f}s, {tokens_in}+{tokens_out} tokens")
    result["_tokens"] = {"in": tokens_in, "out": tokens_out}
    return result


async def llm_call_stream(
    model: str,
    system_prompt: str,
    user_msg: str,
    *,
    label: str = "LLM",
    temperature: float = 0.3,
    max_tokens: int = 8192,
    reasoning_effort: str | None = None,
    on_chunk=None,
    on_reasoning=None,
) -> dict:
    """流式 LLM 调用（OpenAI SDK 直调，支持 DeepSeek Thinking）。
    - reasoning_effort: None 关闭思考, "low"/"medium"/"high"/"max" 开启
    - on_chunk(content_text): 最终回答 token 回调
    - on_reasoning(reasoning_text): 思考过程 token 回调"""
    thinking_enabled = reasoning_effort is not None
    _index(label, f"model={model} T={temperature} reasoning={reasoning_effort}")

    client = AsyncOpenAI(
        api_key=get_api_key(),
        base_url=DEEPSEEK_BASE_URL,
        timeout=300.0,
    )
    t0 = time.time()
    full_text = ""
    reasoning_text = ""
    error_msg = None

    try:
        create_kwargs: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if thinking_enabled:
            create_kwargs["reasoning_effort"] = reasoning_effort
            create_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
        else:
            create_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

        stream = await client.chat.completions.create(**create_kwargs)

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            rc = getattr(delta, 'reasoning_content', None)
            if rc:
                reasoning_text += rc
                if on_reasoning:
                    await on_reasoning(rc)

            ct = delta.content or ""
            if ct:
                full_text += ct
                if on_chunk:
                    await on_chunk(ct)

    except asyncio.CancelledError:
        elapsed = time.time() - t0
        _index(label, f"CANCELLED {elapsed:.1f}s")
        _write_log(label, system_prompt, user_msg, full_text, reasoning_text,
                   elapsed, 0, 0, error="CancelledError: 任务被取消")
        raise
    except Exception as e:
        elapsed = time.time() - t0
        error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        _index(label, f"FAIL {elapsed:.1f}s {e}")
        _write_log(label, system_prompt, user_msg, full_text, reasoning_text,
                   elapsed, 0, 0, error=error_msg)
        raise

    elapsed = time.time() - t0
    content = full_text.strip()
    tokens_out = len(content) // 3
    tokens_in = len(system_prompt + user_msg) // 3
    r_len = len(reasoning_text)
    _index(label, f"{elapsed:.1f}s reasoning={r_len}c ~{tokens_in}+~{tokens_out} tok")

    # JSON 解析：优先 content；失败则从 reasoning_text 反向搜 {
    parsed = None
    parse_err_detail = None
    src_name = "content"
    for source_text, sname in [(content, "content"), (reasoning_text.strip(), "reasoning")]:
        if not source_text and sname == "content":
            continue  # content 为空直接跳
        if not source_text.strip():
            continue
        txt = source_text
        if txt.startswith("```"):
            txt = "\n".join(txt.split("\n")[1:-1])
        try:
            parsed = json.loads(txt)
            src_name = sname
            break
        except json.JSONDecodeError:
            start = txt.find("{")
            end = txt.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    parsed = json.loads(txt[start:end])
                    src_name = sname
                    break
                except json.JSONDecodeError:
                    pass
            # reasoning 反向重试
            if parsed is None and sname == "reasoning":
                brace_positions = [i for i, c in enumerate(txt) if c == "{"]
                for bp in reversed(brace_positions[:-1]):
                    try:
                        parsed = json.loads(txt[bp:end])
                        src_name = sname
                        break
                    except json.JSONDecodeError:
                        continue
        if parsed:
            break

    if parsed is None:
        parse_err_detail = (
            f"content ({len(content)} chars):\n{content[:500]}\n\n"
            f"reasoning tail ({len(reasoning_text)} chars):\n{reasoning_text[-500:]}"
        )
        _write_log(label, system_prompt, user_msg, content, reasoning_text,
                   elapsed, tokens_in, tokens_out, parse_error_detail=parse_err_detail)
        raise RuntimeError(
            f"{label} JSON stream 解析失败\n"
            f"  content({len(content)}c): {content[:200]}\n"
            f"  reasoning({len(reasoning_text)}c): ...{reasoning_text[-200:]}"
        )

    _write_log(label, system_prompt, user_msg, content, reasoning_text,
               elapsed, tokens_in, tokens_out)
    print(f"  [{label}] STREAM {elapsed:.1f}s, reasoning={r_len}c, {len(full_text)}c output, from={src_name}")
    parsed["_tokens"] = {"in": tokens_in, "out": tokens_out}
    return parsed
