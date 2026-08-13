"""A组扩展验收测试：多套方案对比生成（性价比版 vs 舒适版）"""
import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_variants():
    """并行生成两套对比方案，验证差异与结构完整性"""
    print("=== 测试: 对比方案生成（variants=true）===")
    resp = client.post("/api/plans/generate", json={
        "requirement": "成都3天2夜，两个人，预算4000，喜欢美食和历史文化，不要购物",
        "variants": True,
    })
    assert resp.status_code == 200, f"生成失败: {resp.status_code} {resp.text}"
    result = resp.json()

    # 1. 变体结构完整
    variants = result.get("variants", {})
    assert "budget" in variants and "comfort" in variants, "缺少变体"
    print(f"变体: {variants['budget']['label']} / {variants['comfort']['label']}")

    # 2. 每套方案完整（计划/引用/过程/天气/校验）
    for key in ("budget", "comfort"):
        v = variants[key]
        plan = v["plan"]
        assert plan.get("basic_info") and plan.get("daily_schedule"), f"{key} 方案结构不完整"
        assert v.get("references") is not None, f"{key} 缺少引用"
        assert len(v.get("agent_trace", [])) >= 9, f"{key} Agent过程不完整: {len(v.get('agent_trace', []))}节点"
        print(f"  [{v['label']}] 预算:¥{plan['basic_info'].get('total_budget')} "
              f"| 天数:{len(plan.get('daily_schedule', []))} | 引用:{len(v['references'])}条 "
              f"| 酒店:{plan.get('hotel_recommendation', {}).get('name', '?')}")

    # 3. 两套方案应有差异（预算或酒店不同）
    p1 = variants["budget"]["plan"]
    p2 = variants["comfort"]["plan"]
    b1 = p1["basic_info"].get("total_budget", 0)
    b2 = p2["basic_info"].get("total_budget", 0)
    h1 = p1.get("hotel_recommendation", {}).get("name", "")
    h2 = p2.get("hotel_recommendation", {}).get("name", "")
    assert b1 != b2 or h1 != h2, f"两套方案无差异（预算{b1}/{b2}，酒店{h1}/{h2}）"
    print(f"  差异验证: 预算 {b1} vs {b2}，酒店「{h1}」vs「{h2}」")

    # 4. 引用带坐标（地图渲染需要）
    refs = variants["budget"]["references"]
    att_refs = [r for r in refs if r.get("type") == "attraction"]
    if att_refs:
        has_coord = all(r.get("coordinates") for r in att_refs)
        assert has_coord, "景点引用缺少坐标"
        print(f"  坐标验证: {len(att_refs)} 个景点引用均带坐标 ✓")

    # 5. 单方案模式不受影响
    resp2 = client.post("/api/plans/generate", json={
        "requirement": "昆明3天2夜，两个人，预算3000，喜欢自然风光",
    })
    assert resp2.status_code == 200, f"单方案模式异常: {resp2.status_code}"
    assert "plan" in resp2.json() and "variants" not in resp2.json()
    print("  单方案模式回归正常 ✓")

    print("\n✅ 对比方案生成测试全部通过")


if __name__ == "__main__":
    test_variants()
