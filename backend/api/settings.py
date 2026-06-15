import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from config import get_settings, set_api_key, get_api_key, DEEPSEEK_BASE_URL

router = APIRouter()


class SettingsUpdate(BaseModel):
    api_key: str
    api_base_url: str | None = None


class SettingsResponse(BaseModel):
    api_key_configured: bool
    api_key_masked: str
    api_base_url: str


@router.get("", response_model=SettingsResponse)
async def get_current_settings():
    """获取当前设置（API key 脱敏）。"""
    return get_settings()


@router.put("")
async def update_settings(req: SettingsUpdate):
    """更新 API Key 和端点 URL。"""
    if not req.api_key.strip():
        raise HTTPException(status_code=400, detail="API Key 不能为空")
    set_api_key(req.api_key.strip())
    # 立即刷新模块级变量
    import config
    config.DEEPSEEK_API_KEY = config.get_api_key()
    return {"status": "saved", "api_key_configured": True}


@router.post("/validate")
async def validate_api_key():
    """测试当前 API Key 是否有效。"""
    import config
    key = config.get_api_key()
    if not key:
        return {"valid": False, "message": "未配置 API Key"}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url=config.DEEPSEEK_BASE_URL)
        t0 = time.time()
        response = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5,
        )
        elapsed = time.time() - t0
        return {
            "valid": True,
            "message": f"连接成功 ({elapsed:.1f}s)",
            "model_used": config.DEEPSEEK_MODEL,
        }
    except Exception as e:
        msg = str(e)
        # 提取关键错误信息
        if "401" in msg or "unauthorized" in msg.lower() or "invalid" in msg.lower():
            return {"valid": False, "message": "API Key 无效或已过期"}
        elif "402" in msg or "insufficient" in msg.lower():
            return {"valid": False, "message": "账户余额不足"}
        elif "429" in msg or "rate" in msg.lower():
            return {"valid": False, "message": "请求过于频繁，稍后重试"}
        else:
            return {"valid": False, "message": msg[:200]}
