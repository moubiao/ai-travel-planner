"""新城市知识库生成：DeepSeek 辅助生产结构化数据（LLM生成 + 规则校验 + 高德POI校正）

用法（backend 目录下）：
    python gen_city_kb.py chongqing      # 生成重庆全部模块
    python gen_city_kb.py chongqing foods  # 只生成美食模块

流程：
1. 按覆盖矩阵（类型/区域/价位/室内外）Prompt 生成各模块 JSON
2. 规则校验：ID 规范、必填字段、数值范围、坐标在中国范围
3. 写入 knowledge/{city}/ 目录（source 标注 LLM生成+人工抽检）
4. 提示运行 verify_knowledge.py 做高德 POI 坐标校正

生成的数据必须经过 verify_knowledge.py 校验 + 人工抽检后方可使用。
"""
import json
import sys
from datetime import date
from pathlib import Path

from app.services import llm_service

KB = Path(__file__).resolve().parent / "knowledge"
TODAY = date.today().isoformat()

# 城市配置：代码 / 中文名 / 景点ID前缀 / 风格标签 / 主要区域（Prompt 用）
CITY_CONFIG = {
    "chongqing": {
        "code": "chongqing", "name": "重庆", "prefix": "cq",
        "style": "山城魔幻地形、两江夜景、火锅美食、抗战历史",
        "areas": "渝中区（解放碑/洪崖洞/李子坝）、江北区（观音桥）、南岸区（南山/弹子石）、沙坪坝区（磁器口/大学城）、九龙坡区、渝北区、远郊（武隆喀斯特/大足石刻/涪陵/酉阳桃花源）",
        "attractions": 28, "foods": 18, "hotels": 12,
    },
    "dali": {
        "code": "dali", "name": "大理", "prefix": "dl",
        "style": "洱海苍山、白族风情、慢生活、风花雪月",
        "areas": "大理古城、下关市区、洱海周边（才村/龙龛/海东）、喜洲古镇、双廊古镇、宾川县（鸡足山）、剑川县（沙溪古镇）、漾濞县",
        "attractions": 24, "foods": 15, "hotels": 10,
    },
    "lijiang": {
        "code": "lijiang", "name": "丽江", "prefix": "lj",
        "style": "纳西古城、玉龙雪山、茶马古道、高原风光",
        "areas": "丽江古城（大研）、束河古镇、白沙古镇、玉龙雪山、拉市海、宁蒗县（泸沽湖）、永胜县",
        "attractions": 24, "foods": 15, "hotels": 10,
    },
    "xian": {
        "code": "xian", "name": "西安", "prefix": "xa",
        "style": "十三朝古都、秦汉唐历史、古城墙、美食之都",
        "areas": "雁塔区（大雁塔/大唐不夜城）、碑林区（钟楼/城墙）、莲湖区（回民街）、未央区、临潼区（兵马俑/华清宫）、灞桥区（白鹿原）、蓝田县",
        "attractions": 30, "foods": 20, "hotels": 15,
    },
}

ATTR_SCHEMA = """{{
  "id": "{prefix}_att_001",
  "name": "景点名",
  "category": "自然风光/人文古迹/地标打卡/休闲公园/博物馆/主题乐园",
  "location": "所在区+具体地点",
  "coordinates": [经度, 纬度],
  "open_time": "开放时间，如 08:00-17:30 或 全天开放",
  "ticket": 门票价格(元, 0=免费),
  "recommend_season": "推荐季节",
  "visit_duration": "游玩时长，如 2-3小时",
  "tags": ["标签1", "标签2", "标签3"],
  "indoor_outdoor": "indoor 或 outdoor",
  "description": "80字以内简介",
  "transport": "交通方式"
}}"""

FOOD_SCHEMA = """{{
  "id": "{prefix}_food_001",
  "name": "店名/美食",
  "category": "类型（火锅/米线/小吃/正餐/饮品/老字号等）",
  "area": "所在区域",
  "price_per_person": 人均价格(元),
  "recommend_time": "推荐时段（早餐/午餐/晚餐/夜宵）",
  "tags": ["标签1", "标签2"],
  "description": "60字以内简介",
  "signature_dish": "招牌菜"
}}"""

HOTEL_SCHEMA = """{{
  "id": "{prefix}_hotel_001",
  "name": "酒店名",
  "area": "所在区域",
  "price_per_night": 每晚价格(元),
  "stars": 星级(2-5整数),
  "tags": ["档次标签", "位置标签"],
  "description": "60字以内简介"
}}"""


def build_prompt(city: dict, module: str) -> str:
    """构建模块生成提示词"""
    name, style, areas = city["name"], city["style"], city["areas"]
    if module == "attractions":
        n = city["attractions"]
        schema = ATTR_SCHEMA.format(prefix=city["prefix"])
        coverage = f"""覆盖要求（必须满足）：
- 类型覆盖：自然风光/人文古迹/地标打卡/休闲公园/博物馆/主题乐园 各至少 3 个（总量 {n} 个）
- 区域覆盖：市中心 40%、主城区 35%、远郊 25%（参考区域：{areas}）
- 价位覆盖：免费至少 8 个、低价(20-60元) 8 个、高价(100元以上) 4 个
- 室内(indoor)至少 6 个
- 必须是真实存在、有代表性的景点，不要虚构"""
    elif module == "foods":
        n = city["foods"]
        schema = FOOD_SCHEMA.format(prefix=city["prefix"])
        coverage = f"""覆盖要求：
- 包含本地代表性美食类型（结合城市特色：{style}）
- 人均价格覆盖 15-300 元区间
- 分布在不同区域
- 必须是真实存在的店铺或特色美食，不要虚构"""
    else:
        n = city["hotels"]
        schema = HOTEL_SCHEMA.format(prefix=city["prefix"])
        coverage = f"""覆盖要求：
- 三档齐全：经济型(150-300元) 40%、中端(300-500元) 35%、品质(500元以上) 25%
- 分布在不同区域（参考区域：{areas}）
- 优先真实存在的连锁品牌或知名酒店，不要虚构"""

    return f"""你是旅游数据整理专家，请为「{name}」整理 {n} 个{ {'attractions': '代表性景点', 'foods': '特色美食/餐厅', 'hotels': '推荐酒店'}[module] }，输出 JSON 数组。

【{name}城市特色】{style}

【每个条目字段说明】
{schema}

【{coverage}】

只输出 JSON 数组，不要输出任何其他内容。"""


def validate_items(items: list, module: str, city: dict) -> list[str]:
    """规则校验，返回问题列表"""
    prefix = city["prefix"]
    type_abbr = {"attractions": "att", "foods": "food", "hotels": "hotel"}[module]
    problems = []
    seen_ids = set()
    for i, item in enumerate(items):
        item_id = item.get("id", "")
        if not item_id.startswith(f"{prefix}_{type_abbr}_"):
            problems.append(f"[{i}] ID 不规范: {item_id}")
        if item_id in seen_ids:
            problems.append(f"[{i}] ID 重复: {item_id}")
        seen_ids.add(item_id)

        if module == "attractions":
            for field in ("name", "category", "location", "coordinates", "open_time",
                          "ticket", "recommend_season", "visit_duration", "tags",
                          "indoor_outdoor", "description", "transport"):
                if field not in item:
                    problems.append(f"[{i}] 缺字段 {field}")
            coord = item.get("coordinates", [])
            if not (isinstance(coord, list) and len(coord) == 2
                    and 97 <= coord[0] <= 110 and 20 <= coord[1] <= 43):
                problems.append(f"[{i}] 坐标异常: {coord}")
            if not isinstance(item.get("ticket"), (int, float)) or item.get("ticket") < 0:
                problems.append(f"[{i}] 门票异常: {item.get('ticket')}")
        elif module == "foods":
            for field in ("name", "category", "area", "price_per_person", "recommend_time", "tags", "description", "signature_dish"):
                if field not in item:
                    problems.append(f"[{i}] 缺字段 {field}")
            if not isinstance(item.get("price_per_person"), (int, float)) or item.get("price_per_person") <= 0:
                problems.append(f"[{i}] 人均异常: {item.get('price_per_person')}")
        else:
            for field in ("name", "area", "price_per_night", "stars", "tags", "description"):
                if field not in item:
                    problems.append(f"[{i}] 缺字段 {field}")
            if not isinstance(item.get("price_per_night"), (int, float)) or item.get("price_per_night") <= 0:
                problems.append(f"[{i}] 房价异常: {item.get('price_per_night')}")
            if not isinstance(item.get("stars"), int) or not (1 <= item["stars"] <= 5):
                problems.append(f"[{i}] 星级异常: {item.get('stars')}")
    return problems


def gen_module(city_code: str, module: str) -> None:
    """生成单个模块并写入文件"""
    city = CITY_CONFIG[city_code]
    name = city["name"]
    print(f"=== 生成 {name} {module} ===")

    prompt = build_prompt(city, module)
    messages = [
        {"role": "system", "content": "你是严谨的旅游数据整理专家，输出的数据必须真实、准确、结构化。"},
        {"role": "user", "content": prompt},
    ]
    raw = llm_service.chat_json(messages, temperature=0.3, max_tokens=8000)
    items = json.loads(raw)
    if not isinstance(items, list):
        raise RuntimeError(f"LLM 输出不是数组: {type(items)}")

    # 规则校验
    problems = validate_items(items, module, city)
    if problems:
        print(f"⚠️ 校验发现 {len(problems)} 个问题（前10个）：")
        for p in problems[:10]:
            print(f"  - {p}")

    # 数据加工：补 source 字段
    key = module
    for item in items:
        item["source"] = "LLM生成+人工抽检"
        item["verified_at"] = ""

    # 写入文件（保留 meta）
    target = KB / city_code
    target.mkdir(parents=True, exist_ok=True)
    fname = {"attractions": "attractions.json", "foods": "foods.json", "hotels": "hotels.json"}[module]
    fpath = target / fname
    data = {
        "city": city_code,
        "city_name": name,
        key: items,
        "meta": {
            "version": "1.0",
            "updated_at": TODAY,
            "verify_status": "pending",
            "source": "LLM生成+人工抽检，坐标待高德POI校验",
        },
    }
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 已写入 {len(items)} 条 -> {fpath.relative_to(KB.parent)}")
    print(f"⚠️ 下一步：python verify_knowledge.py 进行高德坐标校正，然后人工抽检")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in CITY_CONFIG:
        print("用法: python gen_city_kb.py <city> [module]")
        print(f"城市: {', '.join(CITY_CONFIG.keys())}")
        print("模块: attractions / foods / hotels（省略则全部）")
        return
    city = sys.argv[1]
    module = sys.argv[2] if len(sys.argv) > 2 else None
    targets = [module] if module else ["attractions", "foods", "hotels"]
    for m in targets:
        gen_module(city, m)
    print(f"\n全部完成。请运行 python verify_knowledge.py 校验 {city} 坐标")


if __name__ == "__main__":
    main()
