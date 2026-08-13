"""和风天气配置验证脚本：读取 .env 配置，调用 V1 接口获取成都 3 天预报"""
import os

# 绕过本机异常的 Windows 代理设置，确保直连和风天气
for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(var, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

from app.services import weather_service

print("=" * 50)
print("配置检查：")
print(f"  QWEATHER_API_KEY 已配置: {bool(weather_service.config.QWEATHER_API_KEY)}")
print(f"  QWEATHER_API_HOST 已配置: {bool(weather_service.config.QWEATHER_API_HOST)}")
if not weather_service.config.QWEATHER_API_KEY or not weather_service.config.QWEATHER_API_HOST:
    print("\n❌ 配置缺失：请确认 backend/.env 中已填写 QWEATHER_API_KEY 和 QWEATHER_API_HOST")
    raise SystemExit(1)

print("\n正在调用和风天气 V1 接口（成都，3 天预报）...")
result = weather_service.get_weather("chengdu", days=3)

print(f"\n返回结果：is_demo = {result['is_demo']}")
if result["is_demo"]:
    print("❌ 仍在使用演示数据 —— 接口调用失败，原因见后端日志（接口异常时会打印）")
    raise SystemExit(1)

print("✅ 真实天气数据获取成功！")
for day in result["days"]:
    rain_flag = " 🌧️雨天" if day["is_rain"] else ""
    print(f"  {day['date']}  {day['text_day']}  {day['temp_min']}~{day['temp_max']}°C  降水{day['precip_prob']}%{rain_flag}")
