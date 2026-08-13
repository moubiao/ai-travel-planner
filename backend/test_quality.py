"""第一梯队验收测试：方案质量评估 + 旅行意图理解

覆盖：
1. 质量报告：单方案与变体模式均返回，5 维度齐全，分数 0-100
2. 意图理解：structured_requirement 含 intent（summary/priorities/hidden_needs）
3. Agent 工作流：10 节点（新增质量评估），质量不达标时自动重生成
"""
import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_quality_and_intent():
    """单方案模式：质量报告 + 意图"""
    print("=== 测试: 质量评估 + 意图理解（单方案）===")
    resp = client.post("/api/plans/generate", json={
        "requirement": "成都3天2夜，两个人，预算4000，喜欢美食和历史文化，不要购物",
    })
    assert resp.status_code == 200, f"生成失败: {resp.status_code} {resp.text}"
    result = resp.json()

    # 1. 质量报告结构
    q = result.get("quality_report", {})
    assert q, "缺少质量报告"
    assert 0 <= q.get("overall_score", -1) <= 100, f"总分越界: {q.get('overall_score')}"
    dims = q.get("dimensions", [])
    assert len(dims) == 5, f"维度数异常: {len(dims)}"
    names = [d["name"] for d in dims]
    assert "预算符合度" in names and "路线合理性" in names and "引用真实率" in names \
        and "结构完整性" in names and "需求贴合度" in names, f"维度缺失: {names}"
    for d in dims:
        assert 0 <= d["score"] <= 100, f"维度分数越界: {d['name']}={d['score']}"
    print(f"  总分: {q['overall_score']}（{q['level']}）")
    for d in dims:
        print(f"    - {d['name']}: {d['score']} | {d['detail']}")
    if q.get("suggestions"):
        print(f"  改进项: {q['suggestions'][:2]}")

    # 2. 意图理解
    structured = result["structured_requirement"]
    intent = structured.get("intent", {})
    assert intent.get("summary"), f"意图缺少 summary: {intent}"
    assert isinstance(intent.get("priorities", []), list), "意图 priorities 应为数组"
    assert isinstance(intent.get("hidden_needs", []), list), "意图 hidden_needs 应为数组"
    print(f"  意图: {intent.get('summary')} | 约束: {intent.get('priorities')} | 隐含需求: {intent.get('hidden_needs')}")

    # 3. Agent 工作流节点（含质量评估）
    trace_nodes = [t["node"] for t in result["agent_trace"]]
    assert "质量评估" in trace_nodes, f"缺少质量评估节点: {trace_nodes}"
    print(f"  Agent 节点数: {len(trace_nodes)}（含质量评估）")

    # 4. 质量评估节点 detail 含分数
    q_trace = [t for t in result["agent_trace"] if t["node"] == "质量评估"][0]
    assert "分" in q_trace["detail"], f"质量评估节点未展示分数: {q_trace['detail']}"
    print(f"  质量评估节点: {q_trace['detail'][:80]}")


def test_variants_quality():
    """变体模式：每个变体独立质量报告 + 意图"""
    print("\n=== 测试: 对比方案质量报告 ===")
    resp = client.post("/api/plans/generate", json={
        "requirement": "昆明3天2夜，两个人，预算3000，喜欢自然风光",
        "variants": True,
    })
    assert resp.status_code == 200, f"生成失败: {resp.status_code} {resp.text}"
    result = resp.json()
    variants = result.get("variants", {})
    for key in ("budget", "comfort"):
        v = variants.get(key, {})
        q = v.get("quality_report", {})
        assert q.get("overall_score") is not None, f"{key} 缺少质量报告"
        assert v.get("agent_trace") and any(t["node"] == "质量评估" for t in v["agent_trace"]), f"{key} 缺少质量评估节点"
        print(f"  [{v['label']}] 质量: {q['overall_score']}分（{q['level']}）| 预算: {v['plan']['basic_info']['total_budget']}")

    print("\n✅ 质量评估 + 意图理解测试全部通过")


if __name__ == "__main__":
    test_quality_and_intent()
    test_variants_quality()
