"""全局配置：从 .env 读取 API 密钥等环境变量"""
import os

from dotenv import load_dotenv

# 加载 backend 目录下的 .env 文件
load_dotenv()

# DeepSeek API 配置（沿用 AI记账本 的接入方式，DeepSeek兼容OpenAI协议）
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

# 是否开启思考模式（默认关闭：更快、更省，且支持 temperature 参数）
# DeepSeek 新版本模型默认开启思考，会消耗大量 token 导致输出为空
DEEPSEEK_THINKING = os.getenv("DEEPSEEK_THINKING", "false").lower() == "true"

# 和风天气 API（https://dev.qweather.com 注册获取，未配置时使用演示数据）
QWEATHER_API_KEY = os.getenv("QWEATHER_API_KEY", "")
# 和风天气 API Host：控制台「API Host」获取的项目专属域名（如 https://abcxyz.qweatherapi.com）
QWEATHER_API_HOST = os.getenv("QWEATHER_API_HOST", "")


def get_weather_demo_mode() -> str:
    """天气演示模式：auto=随机 / rain=强制有雨 / sunny=强制晴天

    用函数动态读取，支持运行时切换（测试与演示需要）
    """
    return os.getenv("WEATHER_DEMO_MODE", "auto")

# 高德地图 API（https://lbs.amap.com 注册获取，未配置时用坐标计算兜底）
AMAP_API_KEY = os.getenv("AMAP_API_KEY", "")
