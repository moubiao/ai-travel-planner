"""LLM服务层：统一封装 DeepSeek API 调用"""
from openai import OpenAI

from app import config

_client = None


def get_client() -> OpenAI:
    """懒加载 OpenAI 客户端（DeepSeek 兼容 OpenAI 协议）"""
    global _client
    if _client is None:
        if not config.DEEPSEEK_API_KEY:
            raise RuntimeError("未配置 DEEPSEEK_API_KEY，请复制 .env.example 为 .env 并填入密钥")
        _client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
        )
    return _client


def _extra_body() -> dict:
    """根据配置决定是否开启思考模式（默认关闭，避免推理 token 占满输出）"""
    if config.DEEPSEEK_THINKING:
        return {"thinking": {"type": "enabled"}}
    return {"thinking": {"type": "disabled"}}


def chat(messages: list[dict], temperature: float = 0.7, max_tokens: int = 4096) -> str:
    """通用对话调用，返回文本内容"""
    resp = get_client().chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body=_extra_body(),
    )
    return resp.choices[0].message.content.strip()


def chat_json(messages: list[dict], temperature: float = 0.3, max_tokens: int = 4096) -> str:
    """JSON模式调用：强制模型输出合法 JSON（结构化需求 / 旅行方案）"""
    resp = get_client().chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        extra_body=_extra_body(),
    )
    return resp.choices[0].message.content.strip()
