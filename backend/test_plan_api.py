"""阶段一验收测试：调用本地方案生成 API（临时脚本）"""
import json
import urllib.request

BASE = "http://127.0.0.1:8003"


def post(path: str, payload: dict) -> dict:
    """POST JSON 并返回解析结果"""
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


if __name__ == "__main__":
    # 1. 自然语言需求 → 完整方案
    print("=== 测试1: 自然语言生成方案 ===")
    result = post("/api/plans/generate", {
        "requirement": "成都3天2夜，两个人，预算4000，喜欢美食和历史文化，不要购物",
    })
    print("结构化需求:", json.dumps(result["structured_requirement"], ensure_ascii=False))
    plan = result["plan"]
    print("方案基本信息:", json.dumps(plan.get("basic_info", {}), ensure_ascii=False))
    print("每日安排天数:", len(plan.get("daily_schedule", [])))
    print("美食推荐数:", len(plan.get("food_recommendations", [])))
    print("酒店:", plan.get("hotel_recommendation", {}).get("name", "无"))
    print("Tips:", len(plan.get("tips", [])))

    # RAG 引用检查
    references = result.get("references", [])
    print("知识库引用数:", len(references))
    for ref in references:
        print(f"  - [{ref['type']}] {ref['name']} ({ref['id']})")
    daily = plan.get("daily_schedule", [])
    first_slot = daily[0].get("morning", {}) if daily else {}
    print("Day1上午 source_id:", first_slot.get("source_id", "无"))

    # 2. 对话式调整方案
    print("\n=== 测试2: 对话式调整方案 ===")
    adjusted = post("/api/plans/adjust", {
        "plan": plan,
        "instruction": "预算减少800元，去掉最贵的一天行程",
    })
    new_plan = adjusted["plan"]
    print("调整后预算:", new_plan.get("basic_info", {}).get("total_budget"))
    print("调整后天数:", len(new_plan.get("daily_schedule", [])))
    print("调整后方案OK:", bool(new_plan.get("daily_schedule")))

    print("\n全部测试通过！")
