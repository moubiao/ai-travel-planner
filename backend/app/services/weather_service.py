"""天气服务：和风天气 API 查询（未配置 key 时返回演示数据）

- 已配置 QWEATHER_API_HOST + QWEATHER_API_KEY：调用和风天气 V1 接口（经纬度 + X-QW-Api-Key 认证）
- 未配置：返回演示天气（可配置雨天场景，用于演示 Agent 的天气感知调整）

注册与配置：https://dev.qweather.com 注册 → 控制台创建项目 → 创建 API KEY 凭据 →
在控制台「API Host」获取项目专属域名，填入 .env 的 QWEATHER_API_HOST 与 QWEATHER_API_KEY
"""
import random
from datetime import date, datetime, timedelta, timezone

import requests

from app import config

# 和风天气 V1 每日预报接口：GET {host}/weather/v1/daily/{lat}/{lon}
# 认证方式：请求头 X-QW-Api-Key: <API KEY>（2026 年起主推，旧 v7 接口已弃用）

# 城市代表坐标（经度, 纬度）——用于天气查询（V1 接口基于经纬度）
# 覆盖全部 6 个知识库城市
CITY_COORDS = {
    "chengdu": (104.0665, 30.5728),    # 天府广场
    "chongqing": (106.5516, 29.5630),  # 解放碑
    "kunming": (102.7184, 25.0406),    # 金马碧鸡坊
    "dali": (100.2676, 25.6065),       # 大理市区
    "lijiang": (100.2330, 26.8550),    # 丽江市
    "xian": (108.9398, 34.3416),       # 西安市中心
}

# 天气现象码 → 中文（和风天气 V1 接口返回 code）
WEATHER_CODE_MAP = {
    "100": "晴", "101": "多云", "102": "少云", "103": "晴间多云", "104": "阴",
    "150": "晴", "151": "多云", "152": "少云", "153": "晴间多云",
    "300": "阵雨", "301": "强阵雨", "302": "雷阵雨", "303": "强雷阵雨",
    "304": "雷阵雨伴冰雹", "305": "小雨", "306": "中雨", "307": "大雨",
    "308": "暴雨", "309": "大暴雨", "310": "特大暴雨", "311": "冻雨",
    "312": "小到中雨", "313": "中到大雨", "314": "大到暴雨", "315": "暴雨到大暴雨",
    "316": "大暴雨到特大暴雨", "317": "雨夹雪", "318": "小到中雪", "319": "中到大雪",
    "320": "大到暴雪", "321": "小到中雨夹雪", "322": "中到大雨夹雪",
    "400": "小雪", "401": "中雪", "402": "大雪", "403": "暴雪",
    "500": "薄雾", "501": "雾", "502": "霾", "503": "扬沙", "504": "浮尘",
    "507": "沙尘暴", "508": "强沙尘暴",
    "515": "浓雾", "800": "晴", "801": "多云", "802": "少云", "803": "晴间多云", "804": "阴",
}


def _is_rain_code(code: str) -> bool:
    """根据天气现象码判断是否降雨（3xx 为各类雨）"""
    return code.startswith("3")


# 天气演示模式：auto=随机 / rain=强制有雨 / sunny=强制晴天（动态读取，支持运行时切换）
def _demo_mode() -> str:
    return config.get_weather_demo_mode()


def _demo_weather(city_code: str, start_date: str | None, days: int) -> list[dict]:
    """生成演示天气数据（无 API key 时使用，用于演示雨天调整能力）"""
    mode = _demo_mode()
    rainy = mode == "rain" or (
        mode == "auto" and random.random() < 0.35
    )
    base_date = date.fromisoformat(start_date) if start_date else date.today() + timedelta(days=3)
    result = []
    for i in range(days):
        d = base_date + timedelta(days=i)
        # 演示模式：第 2 天大概率降雨（模拟行程中段变天）
        is_rain = rainy and (i == 1 or (days > 2 and i == 2))
        temp_min, temp_max = random.randint(12, 18), random.randint(22, 30)
        result.append({
            "date": d.isoformat(),
            "temp_min": temp_min,
            "temp_max": temp_max,
            "text_day": "小雨" if is_rain else random.choice(["多云", "晴", "阴"]),
            "precip_prob": random.randint(60, 95) if is_rain else random.randint(0, 30),
            "is_rain": is_rain,
            "is_demo": True,
        })
    return result


def get_weather(city_code: str, start_date: str | None = None, days: int = 3) -> dict:
    """查询行程期间的天气预报

    返回：{"city": 城市代码, "is_demo": 是否演示数据, "days": [逐日天气]}
    """
    if not config.QWEATHER_API_KEY or not config.QWEATHER_API_HOST:
        return {
            "city": city_code,
            "is_demo": True,
            "days": _demo_weather(city_code, start_date, days),
        }

    coords = CITY_COORDS.get(city_code)
    if not coords:
        return {
            "city": city_code,
            "is_demo": True,
            "days": _demo_weather(city_code, start_date, days),
        }

    # 和风天气 V1 每日预报：GET {host}/weather/v1/daily/{lat}/{lon}?days=N&lang=zh
    # 注意：路径参数顺序为 纬度/经度，而 CITY_COORDS 存的是 (经度, 纬度)
    lon, lat = coords
    # 兼容控制台复制的 Host 不带协议的情况（如 abc1234xyz.def.qweatherapi.com）
    host = config.QWEATHER_API_HOST.strip()
    if not host.startswith(("http://", "https://")):
        host = "https://" + host
    url = f"{host.rstrip('/')}/weather/v1/daily/{lat}/{lon}"
    headers = {"X-QW-Api-Key": config.QWEATHER_API_KEY}
    try:
        resp = requests.get(url, params={"days": days, "lang": "zh"}, headers=headers, timeout=8)
        data = resp.json()
        if data.get("code") not in (None, "0", 0, 200):
            raise ValueError(f"和风天气返回异常: {data.get('code')} {data.get('message', '')}")

        result_days = []
        for item in data.get("days", []):
            # forecastStartTime 为 UTC 时间（如 2026-08-11T16:00Z），+8 小时转为当地日期
            start_time = item.get("forecastStartTime", "")
            if not start_time:
                continue
            try:
                local_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00")) + timedelta(hours=8)
                date_str = local_dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
            # 天气现象：白天时段（daytime.condition），响应自带中文 text
            daytime = item.get("daytime", {}) or {}
            condition = daytime.get("condition", {}) or {}
            code = str(condition.get("code", ""))
            text_day = condition.get("text") or WEATHER_CODE_MAP.get(code, code or "未知")
            # 降水概率（V1 返回 0-1 小数，转百分比）
            precip = daytime.get("precipitation", {}) or {}
            precip_prob = float(precip.get("probability", 0) or 0)
            precip_prob_pct = int(round(precip_prob * 100))
            # 雨天判定：天气现象为雨类（3xx），或降水类型为雨且概率 ≥ 30%
            is_rain = _is_rain_code(code) or (precip.get("type") == "rain" and precip_prob_pct >= 30)
            result_days.append({
                "date": date_str,
                "temp_min": int(round(float(item.get("temperatureMin", {}).get("value", 0) or 0))),
                "temp_max": int(round(float(item.get("temperatureMax", {}).get("value", 0) or 0))),
                "text_day": text_day,
                "precip_prob": precip_prob_pct,
                "is_rain": is_rain,
                "is_demo": False,
            })
        if not result_days:
            raise ValueError("和风天气返回空数据")
        return {"city": city_code, "is_demo": False, "days": result_days[:days]}
    except Exception as exc:  # API 异常时回退演示数据，保证流程可用
        print(f"[weather] 和风天气调用失败，使用演示数据: {exc}")
        return {
            "city": city_code,
            "is_demo": True,
            "days": _demo_weather(city_code, start_date, days),
        }
