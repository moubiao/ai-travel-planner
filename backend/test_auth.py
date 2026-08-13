"""阶段四验收测试：用户系统 + 历史记录

覆盖：注册 → 登录 → 保存方案 → 列表 → 详情 → 删除 → 未认证拦截
"""
import json
import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# 每次运行使用唯一用户名（SQLite 持久化，避免重复注册冲突）
TEST_USER = f"tester_{int(time.time()) % 100000}"
TEST_PASSWORD = "test123456"


def test_register_login():
    """注册 + 登录"""
    print("=== 注册/登录 ===")
    # 注册
    resp = client.post("/api/auth/register", json={"username": TEST_USER, "password": TEST_PASSWORD})
    assert resp.status_code == 200, f"注册失败: {resp.text}"
    data = resp.json()
    assert data["token"] and data["username"] == TEST_USER
    print(f"注册成功: {data['username']}")

    # 重复注册应失败
    resp = client.post("/api/auth/register", json={"username": TEST_USER, "password": TEST_PASSWORD})
    assert resp.status_code == 400, "重复注册应返回 400"

    # 登录
    resp = client.post("/api/auth/login", json={"username": TEST_USER, "password": TEST_PASSWORD})
    assert resp.status_code == 200
    token = resp.json()["token"]
    print(f"登录成功，token: {token[:20]}...")

    # 错误密码应 401
    resp = client.post("/api/auth/login", json={"username": TEST_USER, "password": "wrongpass"})
    assert resp.status_code == 401, "错误密码应 401"
    print("错误密码校验通过")

    return token


def test_history(token: str):
    """历史方案：保存/列表/详情/删除 + 未认证拦截"""
    print("\n=== 历史方案 ===")
    headers = {"Authorization": f"Bearer {token}"}

    # 未认证访问应 401
    resp = client.get("/api/history/list")
    assert resp.status_code == 401, "未登录应 401"
    print("未认证拦截通过")

    # 保存方案
    plan = {
        "basic_info": {"destination": "成都", "trip_days": 2, "people": 2, "total_budget": 3000},
        "daily_schedule": [{"day": 1, "theme": "市区文化", "morning": {"activity": "宽窄巷子"}}],
        "food_recommendations": [{"name": "蜀九香火锅"}],
        "hotel_recommendation": {"name": "全季酒店"},
        "tips": ["早点出发"],
    }
    resp = client.post("/api/history/save", json={
        "title": "成都2日文化游",
        "requirement": {"destination": "成都", "days": 2},
        "plan": plan,
        "references": [{"id": "cd_att_002", "name": "宽窄巷子", "type": "attraction"}],
    }, headers=headers)
    assert resp.status_code == 200, f"保存失败: {resp.text}"
    plan_id = resp.json()["plan_id"]
    print(f"方案已保存: id={plan_id}")

    # 列表
    resp = client.get("/api/history/list", headers=headers)
    assert resp.status_code == 200
    plans = resp.json()["plans"]
    assert any(p["id"] == plan_id for p in plans), "列表未包含刚保存的方案"
    print(f"方案列表: {len(plans)} 条")

    # 详情
    resp = client.get(f"/api/history/{plan_id}", headers=headers)
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["plan"]["basic_info"]["destination"] == "成都"
    assert len(detail["references"]) == 1
    print(f"方案详情: {detail['title']}, 引用 {len(detail['references'])} 条")

    # 跨用户隔离：错误用户访问应 404
    other_name = f"other_{int(time.time()) % 100000}"
    resp = client.post("/api/auth/register", json={"username": other_name, "password": "other12345"})
    other_token = resp.json()["token"]
    resp = client.get(f"/api/history/{plan_id}", headers={"Authorization": f"Bearer {other_token}"})
    assert resp.status_code == 404, "他人方案应 404"
    print("跨用户隔离通过")

    # 删除
    resp = client.delete(f"/api/history/{plan_id}", headers=headers)
    assert resp.status_code == 200
    resp = client.get(f"/api/history/{plan_id}", headers=headers)
    assert resp.status_code == 404, "删除后应 404"
    print("删除通过")


if __name__ == "__main__":
    token = test_register_login()
    test_history(token)
    print("\n阶段四验收测试全部通过！")
