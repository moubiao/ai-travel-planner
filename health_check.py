"""AI旅行规划助手 - 全项目体检脚本
检查：目录结构 / 关键文件 / 知识库数据 / 模型 / 索引 / 配置 / README
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PASS, FAIL, WARN = "✅", "❌", "⚠️"
issues = []


def check(ok: bool, label: str):
    print(f"{PASS if ok else FAIL} {label}")
    if not ok:
        issues.append(label)


print("========== 1. 目录结构 ==========")
for d in ["backend", "backend/app", "backend/app/api", "backend/app/services",
          "backend/knowledge", "backend/models", "backend/data/faiss_index",
          "frontend", "frontend/src", "frontend/src/components",
          "frontend/src/views", "frontend/src/stores", "docs/screenshots"]:
    check((ROOT / d).is_dir(), f"目录 {d}")

print("\n========== 2. 关键文件 ==========")
for f in ["start.bat", "check_port.py", "README.md", ".gitignore",
          "backend/requirements.txt", "backend/.env.example", "backend/.env",
          "backend/build_index.py", "backend/download_models.py",
          "backend/gen_city_kb.py", "backend/verify_knowledge.py",
          "backend/app/main.py", "backend/app/config.py",
          "backend/app/database.py",
          "backend/app/services/llm_service.py",
          "backend/app/services/rag_service.py",
          "backend/app/services/agent_service.py",
          "backend/app/services/weather_service.py",
          "backend/app/services/map_service.py",
          "backend/app/services/vision_service.py",
          "backend/app/services/quality_service.py",
          "backend/app/services/plan_validator.py",
          "backend/app/services/city_links.py",
          "backend/app/services/knowledge_loader.py",
          "backend/app/api/plans.py", "backend/app/api/rag.py",
          "backend/app/api/agent.py", "backend/app/api/auth.py",
          "backend/app/api/history.py", "backend/app/api/vision.py",
          "frontend/package.json", "frontend/vite.config.js",
          "frontend/.env", "frontend/.env.example",
          "frontend/src/main.js", "frontend/src/api.js",
          "frontend/src/router/index.js", "frontend/src/stores/planStore.js",
          "frontend/src/components/ItineraryMap.vue",
          "frontend/src/components/AuthDialog.vue",
          "frontend/src/views/HomeView.vue", "frontend/src/views/ResultView.vue",
          "frontend/src/views/HistoryView.vue",
          "DEMO_SCRIPT.md", "PITCH_POINTS.md"]:
    check((ROOT / f).is_file(), f"文件 {f}")

print("\n========== 3. 知识库数据（6 城）==========")
cities = ["chengdu", "chongqing", "kunming", "dali", "lijiang", "xian"]
total = {"attractions": 0, "foods": 0, "hotels": 0}
for city in cities:
    city_dir = ROOT / "backend" / "knowledge" / city
    if not city_dir.is_dir():
        check(False, f"城市目录 {city}")
        continue
    for module in ["attractions", "foods", "hotels"]:
        path = city_dir / f"{module}.json"
        if not path.is_file():
            check(False, f"{city}/{module}.json")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            items = data.get(module, [])
            total[module] += len(items)
            # 抽查必需字段
            if items and "id" not in items[0]:
                check(False, f"{city}/{module}.json 缺 id 字段")
        except Exception as e:
            check(False, f"{city}/{module}.json 解析失败: {e}")
print(f"  数据总量: 景点 {total['attractions']} / 美食 {total['foods']} / 酒店 {total['hotels']}")
check(total["attractions"] > 150, f"景点总数 > 150（实际 {total['attractions']}）")
check(total["foods"] > 90, f"美食总数 > 90（实际 {total['foods']}）")
check(total["hotels"] > 70, f"酒店总数 > 70（实际 {total['hotels']}）")

print("\n========== 4. 模型与索引 ==========")
for model, key in [("bge-small-zh-v1.5", "config.json"),
                   ("bge-reranker-base", "config.json"),
                   ("chinese-clip-vit-base-patch16", "config.json")]:
    check((ROOT / "backend" / "models" / model / key).is_file(), f"模型 {model}")
for f in ["index.faiss", "documents.json"]:
    check((ROOT / "backend" / "data" / "faiss_index" / f).is_file(), f"索引 {f}")

print("\n========== 5. 配置（不显示 key 值）==========")
env = (ROOT / "backend" / ".env").read_text(encoding="utf-8") if (ROOT / "backend" / ".env").exists() else ""
for key in ["DEEPSEEK_API_KEY", "QWEATHER_API_KEY", "QWEATHER_API_HOST", "AMAP_API_KEY"]:
    m = re.search(rf"^{key}=.+", env, re.M)
    val = m.group(0).split("=", 1)[1].strip() if m else ""
    ok = bool(val) and val not in ("你的密钥粘贴到这里",)
    print(f"{PASS if ok else FAIL} backend/.env 中 {key} {'已配置' if ok else '缺失/占位'}")
fe_env = (ROOT / "frontend" / ".env").read_text(encoding="utf-8") if (ROOT / "frontend" / ".env").exists() else ""
m = re.search(r"^VITE_AMAP_JS_KEY=.+", fe_env, re.M)
fe_ok = bool(m and m.group(0).split("=", 1)[1].strip())
print(f"{PASS if fe_ok else WARN} frontend/.env 中 VITE_AMAP_JS_KEY {'已配置' if fe_ok else '未配置（地图降级 SVG）'}")

print("\n========== 6. 服务状态 ==========")
import socket
for port, name in [(8003, "后端"), (5173, "前端")]:
    s = socket.socket()
    r = s.connect_ex(("127.0.0.1", port))
    s.close()
    print(f"{PASS if r == 0 else FAIL} 端口 {port}（{name}）{'运行中' if r == 0 else '未运行'}")

print("\n========== 7. Git 状态 ==========")
import subprocess
status = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
print(f"{PASS if not status else WARN} 工作区 {'干净' if not status else '有未提交改动'}")
if status:
    print(status)

print("\n========== 8. 文档 ==========")
readme = (ROOT / "README.md").read_text(encoding="utf-8")
for section in ["核心特性", "界面预览", "系统架构", "快速开始", "知识库", "项目文档" if "项目文档" in readme else "一键启动"]:
    pass
for keyword in ["一键启动", "定位声明", "快速开始"]:
    print(f"{PASS if keyword in readme else FAIL} README 包含「{keyword}」")

print("\n" + "=" * 30)
print(f"体检完成：{len(issues)} 个问题" if issues else "体检完成：全部通过 ✅")
for i in issues:
    print(" -", i)
