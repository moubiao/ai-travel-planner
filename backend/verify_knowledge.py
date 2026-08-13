"""知识库可信度校验：高德 POI 交叉校验景点坐标

流程：
1. 读取所有城市知识库的景点数据（自动发现 knowledge/ 下的城市目录）
2. 每个景点调用高德 POI 搜索（关键词=景点名，city=adcode）
3. 名称匹配 + 坐标对比：
   - 距离 < 1km：✅ 通过（标记 verified_at）
   - 距离 >= 1km 且名称匹配：⚠️ 坐标偏差，自动更新为高德坐标并记录（source 追加高德POI校正）
   - 未找到 POI：❓ 人工检查（标记待确认）
4. 输出校验报告 data/kb_verify_report.md

用法（backend 目录下）：python verify_knowledge.py
前提：.env 已配置 AMAP_API_KEY（Web服务类型）
"""
import json
import os
import time
from datetime import date
from pathlib import Path

# 绕过本机异常的 Windows 代理设置，确保直连高德
for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(var, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

from difflib import SequenceMatcher

import requests

from app import config
from app.services import map_service

KB = Path(__file__).resolve().parent / "knowledge"
REPORT = Path(__file__).resolve().parent / "data" / "kb_verify_report.md"
TODAY = date.today().isoformat()

# 城市目录 → 高德 adcode（校验用）
CITY_ADC = {
    "chengdu": "510100",
    "kunming": "530100",
    "chongqing": "500000",
    "dali": "532900",
    "lijiang": "530700",
    "xian": "610100",
}

POI_URL = "https://restapi.amap.com/v3/place/text"


def search_poi(name: str, adcode: str) -> list[dict]:
    """高德 POI 搜索，返回前 5 个候选 [{name, location}]（空列表表示未检索到）

    带限流间隔与重试（高德个人 key QPS 有限）
    """
    for attempt in range(3):
        try:
            resp = requests.get(
                POI_URL,
                params={
                    "keywords": name,
                    "city": adcode,
                    "key": config.AMAP_API_KEY,
                    "offset": 5,
                    "page": 1,
                    "extensions": "base",
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "1" and data.get("pois"):
                candidates = []
                for poi in data["pois"]:
                    lng, lat = poi["location"].split(",")
                    candidates.append({"name": poi["name"], "location": [float(lng), float(lat)]})
                return candidates
            # 限流/失败：等待后重试
            time.sleep(1.0 * (attempt + 1))
        except Exception:
            time.sleep(1.0 * (attempt + 1))
    return []


def _normalize(s: str) -> str:
    """归一化名称：去括号内容、去空格、小写（括号内通常是分店/区域说明）"""
    import re

    s = s.lower().replace("（", "(").replace("）", ")")
    s = re.sub(r"\(.*?\)", "", s)  # 去掉括号及其内容
    s = re.sub(r"[\s·・]", "", s)
    return s


def best_match(name: str, candidates: list[dict]) -> dict | None:
    """从候选 POI 中选名称最匹配的（相似度 >= 0.5 视为匹配）"""
    target = _normalize(name)
    best = None
    best_ratio = 0.0
    for cand in candidates:
        cname = _normalize(cand["name"])
        # 包含匹配优先
        if target and (target in cname or cname in target):
            return cand
        ratio = SequenceMatcher(None, target, cname).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = cand
    return best if best_ratio >= 0.5 else None


def verify_city(city: str, adcode: str) -> list[dict]:
    """校验一个城市的所有景点，返回结果列表"""
    path = KB / city / "attractions.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    results = []
    changed = False
    for att in data["attractions"]:
        name = att["name"]
        coord = att["coordinates"]
        try:
            candidates = search_poi(name, adcode)
        except Exception as exc:
            results.append({"name": name, "status": "❓ API异常", "detail": str(exc)})
            continue

        poi = best_match(name, candidates) if candidates else None
        if poi is None:
            cand_names = "、".join(c["name"] for c in candidates[:3]) if candidates else "无（可能限流）"
            results.append({"name": name, "status": "❓ 未匹配", "detail": f"候选:{cand_names}，请人工核对名称/坐标"})
            continue

        poi_name, poi_coord = poi["name"], poi["location"]
        dist = map_service.haversine(coord, poi_coord)
        if dist > 50:
            # 偏差过大：疑似跨城同名误匹配，不自动校正，人工确认
            results.append({
                "name": name, "status": "❓ 疑似误匹配",
                "detail": f"偏差 {dist:.0f}km（源：{poi_name}），可能匹配到其他城市同名地点，请人工确认",
            })
            continue
        if dist < 1.0:
            results.append({"name": name, "status": "✅ 通过", "detail": f"距高德坐标 {dist:.2f}km（源：{poi_name}）"})
            att["verified_at"] = TODAY
        else:
            # 坐标偏差：更新为高德坐标（更准），并记录校正
            old = coord
            att["coordinates"] = poi_coord
            att["verified_at"] = TODAY
            if "高德POI校正" not in att.get("source", ""):
                att["source"] = (att.get("source", "人工整理") + "+高德POI校正").strip("+")
            changed = True
            results.append({
                "name": name, "status": "⚠️ 已校正",
                "detail": f"坐标偏差 {dist:.1f}km：{old} → {poi_coord}（源：{poi_name}）",
            })

    data["meta"]["verify_status"] = "verified"
    data["meta"]["verified_at"] = TODAY
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return results


def main() -> None:
    if not config.AMAP_API_KEY:
        print("❌ 未配置 AMAP_API_KEY，请先在 backend/.env 填写")
        return

    print("=" * 60)
    print(f"知识库可信度校验（高德 POI 交叉验证）{TODAY}")
    print("=" * 60)

    all_results = {}
    for city_dir in sorted(KB.iterdir()):
        if not city_dir.is_dir() or city_dir.name not in CITY_ADC:
            continue
        city = city_dir.name
        print(f"\n--- {city} ---")
        results = verify_city(city, CITY_ADC[city])
        all_results[city] = results
        ok = sum(1 for r in results if r["status"].startswith("✅"))
        fixed = sum(1 for r in results if r["status"].startswith("⚠️"))
        manual = sum(1 for r in results if r["status"].startswith("❓"))
        print(f"  景点 {len(results)} 个：✅ {ok} 通过 | ⚠️ {fixed} 已校正 | ❓ {manual} 需人工确认")
        for r in results:
            if not r["status"].startswith("✅"):
                print(f"    {r['status']} {r['name']}: {r['detail']}")

    # 生成报告
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(f"# 知识库可信度校验报告\n\n> 校验日期：{TODAY}\n> 校验方式：高德 POI 搜索交叉验证景点坐标（偏差 <1km 视为通过）\n\n")
        for city, results in all_results.items():
            f.write(f"\n## {city}\n\n| 景点 | 状态 | 说明 |\n|---|---|---|\n")
            for r in results:
                f.write(f"| {r['name']} | {r['status']} | {r['detail']} |\n")
    print(f"\n报告已输出: {REPORT}")


if __name__ == "__main__":
    main()
