"""知识库 schema 升级：为现有城市数据补充来源与版本字段

为每条数据添加：
- source: 数据来源（人工整理 / 高德POI校验 / LLM生成+人工抽检）
- verified_at: 校验日期（空表示待校验）

为每个城市文件添加顶层 meta（版本/更新时间/校验状态）

用法（backend 目录下）：python upgrade_knowledge_schema.py
"""
import json
from datetime import date
from pathlib import Path

KB = Path(__file__).resolve().parent / "knowledge"
TODAY = date.today().isoformat()

# 现有城市（新城市数据生产时按新 schema 直接写）
CITIES = ["chengdu", "kunming"]


def upgrade() -> None:
    for city in CITIES:
        for fname in ["attractions.json", "foods.json", "hotels.json"]:
            path = KB / city / fname
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            key = [k for k in data if isinstance(data[k], list)][0]
            changed = False
            for item in data[key]:
                if "source" not in item:
                    item["source"] = "人工整理"
                    item["verified_at"] = ""
                    changed = True
            if "meta" not in data:
                data["meta"] = {
                    "version": "1.1",
                    "updated_at": TODAY,
                    "verify_status": "pending",
                }
                changed = True
            if changed:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"已升级: {city}/{fname}")
            else:
                print(f"无需升级: {city}/{fname}")


if __name__ == "__main__":
    upgrade()
