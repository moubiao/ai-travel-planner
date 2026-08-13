"""高德地图配置验证脚本：读取 .env 配置，调用距离测量 API 计算成都两景点驾车距离"""
import os

# 绕过本机异常的 Windows 代理设置，确保直连高德
for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(var, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

from app.services import map_service

print("=" * 50)
print("配置检查：")
print(f"  AMAP_API_KEY 已配置: {bool(map_service.config.AMAP_API_KEY)}")
if not map_service.config.AMAP_API_KEY:
    print("\n❌ 配置缺失：请确认 backend/.env 中已填写 AMAP_API_KEY")
    raise SystemExit(1)

print("\n正在调用高德距离测量 API（宽窄巷子 → 成都大熊猫基地）...")
result = map_service.get_distance([104.0577, 30.6721], [104.1482, 30.7366])

print(f"\n返回结果：数据来源 = {result['source']}")
if result["source"] == "haversine":
    print("❌ 仍在使用坐标估算 —— 高德接口调用失败，请检查 key 是否正确")
    raise SystemExit(1)

print("✅ 高德真实驾车数据获取成功！")
print(f"  驾车距离: {result['km']} 公里")
print(f"  预计耗时: {result['minutes']} 分钟")
print("\n说明：配置后 Agent 的路线规划将使用真实驾车距离（无 key 时用直线距离估算兜底）")
