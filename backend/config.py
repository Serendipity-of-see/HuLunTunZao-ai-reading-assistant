import json
import os
from pathlib import Path

# 数据目录（用户本地）
DATA_DIR = Path(os.environ.get("HLTZ_DATA_DIR", Path.home() / ".huluntunzao"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 配置持久化文件
CONFIG_FILE = DATA_DIR / "config.json"

# 数据库路径
DB_PATH = DATA_DIR / "hltz.db"

# DeepSeek API
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_PRO_MODEL = "deepseek-v4-pro"

# Token 预算
TOKEN_BUDGET = 800_000
COMPRESSION_TRIGGER = 600_000

# 分段阈值
ATOM_CHUNK_SIZE = 5000


def _load_config() -> dict:
    """加载用户配置文件。"""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_config(config: dict):
    """保存用户配置文件。"""
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def get_api_key() -> str:
    """获取 API Key。优先环境变量，其次用户配置。"""
    env_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if env_key:
        return env_key
    return _load_config().get("deepseek_api_key", "")


def set_api_key(key: str):
    """持久化保存 API Key。"""
    config = _load_config()
    config["deepseek_api_key"] = key
    _save_config(config)


def get_settings() -> dict:
    """获取所有用户设置（返回时对 key 脱敏）。"""
    key = get_api_key()
    masked = ""
    if key:
        if len(key) > 8:
            masked = key[:4] + "*" * (len(key) - 8) + key[-4:]
        else:
            masked = key[:2] + "*" * (len(key) - 2)
    user_config = _load_config()
    return {
        "api_key_configured": bool(key),
        "api_key_masked": masked,
        "api_base_url": user_config.get("api_base_url", DEEPSEEK_BASE_URL),
    }
