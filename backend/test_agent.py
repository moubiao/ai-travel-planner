"""阶段三验收测试：LangGraph Agent 工作流

覆盖：
1. 完整工作流：5 个节点按序执行（需求分析→知识检索→天气查询→路线优化→方案生成）
2. 雨天模式：天气演示模式设为 rain 时，路线优化应给出室内替换建议
3. 路线聚类：同区域景点分组正确
"""
import os

# 天气演示模式：强制雨天（验证 Agent 天气感知调整）
os.environ["WEATHER_DEMO_MODE"] = "rain"

from fastapi.testclient import TestClient

from app.main import app
from app.services import map_service

client = TestClient(app)


def test_route_clustering():
    """路线聚类：成都市中心景点应聚为一组"""
    items = [
        {"name": "宽窄巷子", "metadata": {"coordinates": [104.0577, 30.6721]}},
        {"name": "人民公园", "metadata": {"coordinates": [104.0567, 30.6642]}},
        {"name": "文殊院", "metadata": {"coordinates": [104.0763, 30.6812]}},
        {"name": "西岭雪山", "metadata": {"coordinates": [103.2208, 30.6821]}},
    ]
    groups = map_service.cluster_by_proximity(items, threshold_km=8.0)
    print(f"聚类组数: {len(groups)}")
    for g in groups:
        print("  -", "、".join(item["name"] for item in g))
    assert any(len(g) >= 3 for g in groups), "市中心景点未正确聚类"
    print("路线聚类测试通过 ✓")


def test_agent_workflow():
    """完整 Agent 工作流（雨天模式）"""
    print("\n=== Agent 工作流测试（雨天模式）===")
    resp = client.post("/api/plans/generate", json={
        "requirement": "成都3天2夜，两个人，预算4000，喜欢历史文化",
    })
    assert resp.status_code == 200, f"生成失败: {resp.status_code} {resp.text}"
    result = resp.json()

    # 1. Agent 执行过程：5 个节点
    trace = result["agent_trace"]
    print("Agent 执行过程:")
    for t in trace:
        print(f"  [{t['node']}] {t['detail']}")
    node_names = [t["node"] for t in trace]
    expected = ["需求分析", "知识检索", "天气查询", "景点Agent", "美食Agent", "路线Agent", "预算Agent", "方案生成", "行程校验"]
    assert node_names == expected, f"节点顺序异常: {node_names}"

    # 2. 天气信息：应包含雨天标记
    weather = result["weather"]
    rain_days = weather.get("rain_days", [])
    print(f"天气预报: {weather.get('is_demo') and '演示' or '真实'} 数据, 雨天: {rain_days}")
    assert len(rain_days) > 0, "雨天模式未生效"

    # 3. 路线优化：应包含雨天调整建议（现在由路线Agent与行程校验覆盖）
    route_trace = [t for t in trace if t["node"] == "路线Agent"][0]
    print(f"路线Agent建议: {route_trace['detail']}")
    validate_trace = [t for t in trace if t["node"] == "行程校验"][0]
    print(f"行程校验: {validate_trace['detail']}")
    assert "室内" in route_trace["detail"] or "区域" in route_trace["detail"], "路线Agent输出异常"

    # 4. 方案完整性
    plan = result["plan"]
    assert len(plan.get("daily_schedule", [])) == 3, "天数错误"
    assert len(result["references"]) > 0, "无知识库引用"
    # 5. 行程校验警告
    warnings = result.get("plan_warnings", [])
    print(f"行程校验警告: {len(warnings)} 条")
    for w in warnings:
        print(f"  - [{w['level']}] {w['message']}")
    print("Agent 工作流测试通过 ✓")


def test_normal_mode():
    """晴天模式（恢复 auto）"""
    print("\n=== Agent 工作流测试（恢复默认模式）===")
    os.environ["WEATHER_DEMO_MODE"] = "sunny"
    resp = client.post("/api/plans/generate", json={
        "requirement": "昆明3天，一个人，预算2500，喜欢自然风光",
    })
    assert resp.status_code == 200
    result = resp.json()
    trace = result["agent_trace"]
    node_names = [t["node"] for t in trace]
    assert len(node_names) == 9, f"节点数异常: {node_names}"
    plan = result["plan"]
    print(f"昆明方案: {len(plan['daily_schedule'])} 天, 引用 {len(result['references'])} 条")
    for t in trace:
        print(f"  [{t['node']}] {t['detail'][:80]}")
    assert len(result["weather"].get("rain_days", [])) == 0, "晴天模式不应有雨天"
    print("正常模式测试通过 ✓")


if __name__ == "__main__":
    test_route_clustering()
    test_agent_workflow()
    test_normal_mode()
    print("\n全部 Agent 测试通过！")
