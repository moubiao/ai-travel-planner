"""旅游知识库数据加载：读取 JSON 数据并转换为可检索的文档"""
import json
from pathlib import Path

# 知识库根目录：backend/knowledge（本文件位于 backend/app/services/ 下）
KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge"

# 支持的旅游城市（新城市数据就绪后在此注册，并重建索引）
CITIES = [
    {"code": "chengdu", "name": "成都"},
    {"code": "chongqing", "name": "重庆"},
    {"code": "kunming", "name": "昆明"},
    {"code": "dali", "name": "大理"},
    {"code": "lijiang", "name": "丽江"},
    {"code": "xian", "name": "西安"},
]

# 城市别名（需求解析用，支持「川渝」「云南」等组合叫法）
CITY_ALIASES = {
    "蓉": "成都", "锦官城": "成都",
    "渝": "重庆", "山城": "重庆",
    "春城": "昆明", "滇": "昆明",
    "风花雪月": "大理",
    "丽江古城": "丽江",
    "长安": "西安", "十三朝古都": "西安",
    "川渝": ["成都", "重庆"],
    "云南": ["昆明", "大理", "丽江"],
    "滇西": ["大理", "丽江"],
}


def _load_json(path: Path) -> dict:
    """读取 JSON 文件（UTF-8）"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _attraction_text(item: dict) -> str:
    """将景点数据拼接为检索文本"""
    return (
        f"{item['name']}。类别：{item['category']}。位于{item['location']}。"
        f"{item['description']} 开放时间：{item['open_time']}。门票：{item['ticket']}元。"
        f"推荐季节：{item['recommend_season']}。游玩时长：{item['visit_duration']}。"
        f"标签：{'、'.join(item['tags'])}。"
    )


def _food_text(item: dict) -> str:
    """将美食数据拼接为检索文本"""
    return (
        f"{item['name']}。类别：{item['category']}。位于{item['area']}。"
        f"{item['description']} 人均：{item['price_per_person']}元。"
        f"推荐时间：{item['recommend_time']}。招牌：{item['signature_dish']}。"
        f"标签：{'、'.join(item['tags'])}。"
    )


def _hotel_text(item: dict) -> str:
    """将酒店数据拼接为检索文本"""
    return (
        f"{item['name']}。位于{item['area']}。{item['description']} "
        f"每晚价格：{item['price_per_night']}元。星级：{item['stars']}星。"
        f"标签：{'、'.join(item['tags'])}。"
    )


def build_documents() -> list[dict]:
    """加载所有城市数据，构造检索文档列表

    每个文档结构：{id, type, city, city_name, name, text, metadata}
    - type: attraction / food / hotel
    - metadata: 用于检索过滤的附加字段
    """
    documents = []
    for city in CITIES:
        city_dir = KNOWLEDGE_DIR / city["code"]
        if not city_dir.exists():
            continue

        # 景点
        attractions = _load_json(city_dir / "attractions.json")["attractions"]
        for item in attractions:
            documents.append({
                "id": item["id"],
                "type": "attraction",
                "city": city["code"],
                "city_name": city["name"],
                "name": item["name"],
                "text": _attraction_text(item),
                "metadata": {
                    "category": item["category"],
                    "ticket": item["ticket"],
                    "indoor_outdoor": item["indoor_outdoor"],
                    "tags": item["tags"],
                    "location": item["location"],
                    "coordinates": item["coordinates"],
                    "source": item.get("source", ""),
                    "verified_at": item.get("verified_at", ""),
                },
            })

        # 美食
        foods = _load_json(city_dir / "foods.json")["foods"]
        for item in foods:
            documents.append({
                "id": item["id"],
                "type": "food",
                "city": city["code"],
                "city_name": city["name"],
                "name": item["name"],
                "text": _food_text(item),
                "metadata": {
                    "category": item["category"],
                    "price_per_person": item["price_per_person"],
                    "area": item["area"],
                    "tags": item["tags"],
                    "source": item.get("source", ""),
                    "verified_at": item.get("verified_at", ""),
                },
            })

        # 酒店
        hotels = _load_json(city_dir / "hotels.json")["hotels"]
        for item in hotels:
            documents.append({
                "id": item["id"],
                "type": "hotel",
                "city": city["code"],
                "city_name": city["name"],
                "name": item["name"],
                "text": _hotel_text(item),
                "metadata": {
                    "price_per_night": item["price_per_night"],
                    "stars": item["stars"],
                    "area": item["area"],
                    "tags": item["tags"],
                    "source": item.get("source", ""),
                    "verified_at": item.get("verified_at", ""),
                },
            })

    return documents


def city_code_to_name(code: str) -> str:
    """城市代码转中文名"""
    for city in CITIES:
        if city["code"] == code:
            return city["name"]
    return code


def city_name_to_code(name: str) -> str:
    """城市中文名（或代码/别名）转城市代码，找不到返回 None"""
    name = name.strip()
    # 别名（如 蓉→成都、渝→重庆）
    if name in CITY_ALIASES and isinstance(CITY_ALIASES[name], str):
        name = CITY_ALIASES[name]
    for city in CITIES:
        if name in (city["code"], city["name"]):
            return city["code"]
    return None


def resolve_cities(value) -> list[str]:
    """将目的地描述解析为城市名列表（支持别名/组合叫法/多城市字符串）

    输入：字符串（"成都重庆" / "川渝" / "成都"）或列表（["成都", "重庆"]）
    输出：城市名列表，如 ["成都", "重庆"]
    """
    if isinstance(value, list):
        result = []
        for v in value:
            for name in resolve_cities(v):
                if name not in result:
                    result.append(name)
        return result
    if not value:
        return []
    value = value.strip()
    # 组合别名（如 川渝 → 成都+重庆、云南 → 昆明+大理+丽江）
    if value in CITY_ALIASES:
        alias = CITY_ALIASES[value]
        if isinstance(alias, list):
            return alias
        return [alias] if any(c["name"] == alias for c in CITIES) else []
    # 单城市直接命中
    if any(value == c["name"] for c in CITIES):
        return [value]
    # 组合字符串：按已知城市名包含匹配（如「成都重庆」「昆明大理丽江」）
    result = []
    for c in CITIES:
        if c["name"] in value:
            result.append(c["name"])
    return result
