"""阶段3多地联游验收测试：多目的地解析 + 组合检索 + 分段排程 + 城市衔接"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_multi_city_chengdu_chongqing():
    """川渝线：成都+重庆 5 天"""
    print("=== 测试1: 成都重庆5天（多城市分段）===")
    resp = client.post("/api/plans/generate", json={
        "requirement": "成都重庆5天4夜，两个人，预算6000，喜欢美食和夜景",
    })
    assert resp.status_code == 200, f"生成失败: {resp.status_code} {resp.text}"
    result = resp.json()
    structured = result["structured_requirement"]
    plan = result["plan"]

    # 1. 多城市解析
    cities = structured.get("cities", [])
    assert len(cities) == 2, f"应解析出2个城市: {cities}"
    assert "成都" in cities and "重庆" in cities, f"城市解析错误: {cities}"
    print(f"  解析城市: {cities}")

    # 2. 方案按城市分段：前段成都、后段重庆（或包含跨城日）
    days = plan.get("daily_schedule", [])
    assert len(days) == 5, f"天数应为5: {len(days)}"
    day_cities = [d.get("city", "") for d in days]
    assert any("成都" in c for c in day_cities) and any("重庆" in c for c in day_cities), \
        f"行程未覆盖两城: {day_cities}"
    print(f"  每日城市: {day_cities}")

    # 3. 知识库引用覆盖两城
    refs = result.get("references", [])
    ref_cities = {r.get("city_name") for r in refs if r.get("city_name")}
    assert "成都" in ref_cities and "重庆" in ref_cities, f"引用未覆盖两城: {ref_cities}"
    print(f"  引用覆盖: {ref_cities}")

    # 4. 意图理解
    intent = structured.get("intent", {})
    print(f"  意图: {intent.get('summary')} | 约束: {intent.get('priorities')}")

    # 5. 质量评估
    q = result.get("quality_report", {})
    print(f"  质量: {q.get('overall_score')}分（{q.get('level')}）")


def test_alias_chuanyu():
    """组合叫法：川渝 = 成都+重庆"""
    print("\n=== 测试2: 组合叫法「川渝」===")
    resp = client.post("/api/plans/generate", json={
        "requirement": "川渝4天3夜，预算5000，喜欢火锅和古镇",
    })
    assert resp.status_code == 200, f"生成失败: {resp.status_code}"
    structured = resp.json()["structured_requirement"]
    cities = structured.get("cities", [])
    assert "成都" in cities and "重庆" in cities, f"川渝解析失败: {cities}"
    print(f"  川渝解析: {cities}")


def test_multi_city_yunnan():
    """云南线：昆明+大理+丽江 6 天"""
    print("\n=== 测试3: 昆明大理丽江6天（三城联游）===")
    resp = client.post("/api/plans/generate", json={
        "requirement": "昆明大理丽江6天5夜，预算8000，喜欢自然风光和慢生活",
    })
    assert resp.status_code == 200, f"生成失败: {resp.status_code}"
    result = resp.json()
    structured = result["structured_requirement"]
    plan = result["plan"]
    cities = structured.get("cities", [])
    assert len(cities) == 3, f"应解析出3城: {cities}"
    day_cities = [d.get("city", "") for d in plan.get("daily_schedule", [])]
    assert len(day_cities) == 6
    # 三城都覆盖
    for c in cities:
        assert any(c in dc for dc in day_cities), f"行程缺少城市 {c}: {day_cities}"
    print(f"  三城解析: {cities}")
    print(f"  每日城市: {day_cities}")
    # 跨城日应包含交通安排（找跨城相邻天）
    for i in range(1, len(day_cities)):
        if day_cities[i] != day_cities[i - 1]:
            slot = plan["daily_schedule"][i].get("morning", {})
            print(f"  跨城日 Day{i+1}: {slot.get('activity', '')[:40]}")


def test_single_city_regression():
    """单城市回归：西安（新城市）"""
    print("\n=== 测试4: 单城市回归（西安）===")
    resp = client.post("/api/plans/generate", json={
        "requirement": "西安3天2夜，两个人，预算4000，喜欢历史文化",
    })
    assert resp.status_code == 200, f"生成失败: {resp.status_code}"
    result = resp.json()
    plan = result["plan"]
    refs = result.get("references", [])
    att_names = [r["name"] for r in refs if r.get("type") == "attraction"]
    assert len(plan.get("daily_schedule", [])) == 3
    assert any("兵马俑" in n or "城墙" in n or "大雁塔" in n or "博物馆" in n for n in att_names), \
        f"西安景点引用异常: {att_names[:8]}"
    print(f"  西安景点引用: {att_names[:8]}")
    q = result.get("quality_report", {})
    print(f"  质量: {q.get('overall_score')}分（{q.get('level')}）")


if __name__ == "__main__":
    test_multi_city_chengdu_chongqing()
    test_alias_chuanyu()
    test_multi_city_yunnan()
    test_single_city_regression()
    print("\n✅ 多地联游测试全部通过")
