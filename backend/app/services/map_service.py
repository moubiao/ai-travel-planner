"""地图服务：高德地图距离 API（未配置 key 时用经纬度 haversine 计算兜底）

用途：Agent 路线优化——计算景点间距离，按地理位置就近安排行程。
"""
import math

import requests

from app import config

AMAP_DISTANCE_URL = "https://restapi.amap.com/v3/distance"


def haversine(coord1: list, coord2: list) -> float:
    """根据经纬度计算两点间球面距离（公里），coord 格式 [经度, 纬度]"""
    lon1, lat1 = map(math.radians, coord1)
    lon2, lat2 = map(math.radians, coord2)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def get_distance(coord1: list, coord2: list) -> dict:
    """获取两地点间距离

    有高德 key 时调用驾车距离 API；否则用 haversine 直线距离兜底。
    返回：{"km": 距离, "minutes": 驾车预估分钟数, "source": "amap"|"haversine"}
    """
    if config.AMAP_API_KEY:
        try:
            origin = f"{coord1[0]},{coord1[1]}"
            dest = f"{coord2[0]},{coord2[1]}"
            resp = requests.get(
                AMAP_DISTANCE_URL,
                params={"origins": origin, "destination": dest, "key": config.AMAP_API_KEY, "type": "1"},
                timeout=8,
            )
            data = resp.json()
            if data.get("status") == "1" and data["results"]:
                km = float(data["results"][0]["distance"]) / 1000
                minutes = int(float(data["results"][0]["duration"]) / 60)
                return {"km": round(km, 1), "minutes": minutes, "source": "amap"}
        except Exception as exc:
            print(f"[map] 高德距离 API 调用失败，使用坐标计算: {exc}")

    km = haversine(coord1, coord2)
    minutes = int(km / 0.6)  # 市区平均车速约 36km/h 的粗略估算
    return {"km": round(km, 1), "minutes": minutes, "source": "haversine"}


def cluster_by_proximity(items: list[dict], threshold_km: float = 8.0) -> list[list[dict]]:
    """按地理位置对景点贪心聚类（同区域景点归为一组，用于行程编排）

    items 需含 metadata.coordinates 或 coordinates 字段，格式 [经度, 纬度]
    """
    groups = []
    remaining = list(items)
    while remaining:
        anchor = remaining.pop(0)
        group = [anchor]
        anchor_coord = _get_coord(anchor)
        if anchor_coord:
            close = []
            for item in remaining:
                coord = _get_coord(item)
                if coord and haversine(anchor_coord, coord) <= threshold_km:
                    close.append(item)
            for item in close:
                remaining.remove(item)
            group.extend(close)
        groups.append(group)
    return groups


def _get_coord(item: dict) -> list | None:
    """从文档中提取经纬度坐标"""
    if "metadata" in item:
        return item["metadata"].get("coordinates")
    return item.get("coordinates")
