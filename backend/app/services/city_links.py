"""城市间交通衔接：高铁参考时长（多城联游的跨城日安排）

数据来源：公开高铁运行时长（常见车次平均值，含进站/候车余量取整）。
仅覆盖知识库已注册城市之间的常用组合。
"""
from app.services.knowledge_loader import CITIES, city_name_to_code

# 城市对（代码）→ 高铁参考时长（分钟）
_TRAIN_MINUTES = {
    # 川渝线
    ("chengdu", "chongqing"): 90,
    # 云南线
    ("kunming", "dali"): 120,
    ("dali", "lijiang"): 120,
    ("kunming", "lijiang"): 200,
    # 跨线
    ("chengdu", "xian"): 200,
    ("chengdu", "kunming"): 340,
    ("chongqing", "xian"): 320,
    ("chongqing", "kunming"): 240,
    ("xian", "kunming"): 320,
}


def get_train_time(city_a: str, city_b: str) -> dict | None:
    """查询两城市间高铁参考时长（城市名或代码均可）

    返回：{"minutes": 分钟, "route": "成都→重庆"} 或 None（无直达数据）
    """
    ca = city_name_to_code(city_a)
    cb = city_name_to_code(city_b)
    if not ca or not cb or ca == cb:
        return None
    minutes = _TRAIN_MINUTES.get((ca, cb)) or _TRAIN_MINUTES.get((cb, ca))
    if not minutes:
        return None
    name_a = next(c["name"] for c in CITIES if c["code"] == ca)
    name_b = next(c["name"] for c in CITIES if c["code"] == cb)
    return {"minutes": minutes, "route": f"{name_a}→{name_b}"}


def format_city_links(cities: list[str]) -> str:
    """将城市列表格式化为 Prompt 注入文本（含高铁衔接建议）

    cities: 城市名列表，如 ["成都", "重庆"]
    返回：如「成都→重庆 高铁约1.5小时，建议安排半天交通时间」
    """
    lines = []
    for i in range(len(cities) - 1):
        link = get_train_time(cities[i], cities[i + 1])
        if link:
            hours = link["minutes"] / 60
            lines.append(
                f"{link['route']} 高铁约{hours:.1f}小时，建议跨城当天上午出发，预留半天交通时间"
            )
        else:
            lines.append(f"{cities[i]}→{cities[i+1]} 暂无直达高铁数据，建议预留大半天交通时间")
    return "\n".join(lines) or "（单城市行程，无需跨城）"
