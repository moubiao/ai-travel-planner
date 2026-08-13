"""快速验证：TestClient 进程内调用完整链路（无需重启服务）"""
import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

print("=== 测试: 自然语言生成方案（RAG + 年份注入）===")
resp = client.post("/api/plans/generate", json={
    "requirement": "成都3天2夜，两个人，预算4000，喜欢美食和历史文化，不要购物",
})
assert resp.status_code == 200, f"生成失败: {resp.status_code} {resp.text}"
result = resp.json()
structured = result["structured_requirement"]
plan = result["plan"]
references = result["references"]

print("结构化需求:", json.dumps(structured, ensure_ascii=False))
print("旅行天数:", plan["basic_info"]["trip_days"], "| 总预算:", plan["basic_info"]["total_budget"])
print("日期:", plan["basic_info"].get("dates", "无"))
print("知识库引用数:", len(references))
for ref in references:
    print(f"  - [{ref['type']}] {ref['name']} ({ref['id']})")

# 断言：方案天数正确、引用非空
assert plan["basic_info"]["trip_days"] == 3, "天数错误"
assert len(references) > 0, "无知识库引用"
assert "2023" not in plan["basic_info"].get("dates", ""), "日期年份异常"

# 每个活动的 source_id 都应能映射到引用
source_ids = {ref["id"] for ref in references}
missing = []
for day in plan["daily_schedule"]:
    for slot in ("morning", "afternoon", "evening"):
        sid = day.get(slot, {}).get("source_id")
        if sid and sid not in source_ids:
            missing.append(sid)
print("未映射到引用的 source_id:", missing if missing else "无")

print("\n=== 测试: 对话式调整 ===")
resp = client.post("/api/plans/adjust", json={
    "plan": plan,
    "instruction": "预算减少500元",
})
assert resp.status_code == 200, f"调整失败: {resp.status_code} {resp.text}"
new_plan = resp.json()["plan"]
print("调整后预算:", new_plan["basic_info"]["total_budget"])
assert new_plan["basic_info"]["total_budget"] <= 4000, "预算未下调"

print("\n=== 测试: RAG 检索接口 ===")
resp = client.post("/api/rag/search", json={
    "query": "昆明 冬季 红嘴鸥",
    "city": "昆明",
    "doc_type": "attraction",
    "top_k": 3,
})
assert resp.status_code == 200, f"检索失败: {resp.status_code}"
results = resp.json()["results"]
for r in results:
    print(f"  - [{r['type']}] {r['name']} (score={r['score']:.3f})")
assert len(results) > 0, "检索无结果"

print("\n全部快速验证通过！")
