"""验证：6 城天气坐标修复后全部走真实数据"""
from app.services import weather_service

for city in ["chengdu", "chongqing", "kunming", "dali", "lijiang", "xian"]:
    r = weather_service.get_weather(city, days=2)
    demo = "⚠️演示" if r["is_demo"] else "✅真实"
    days = " | ".join(f"{d['date']} {d['text_day']} {d['temp_min']}~{d['temp_max']}°C 降水{d['precip_prob']}%" for d in r["days"])
    print(f"{city:10s} {demo}  {days}")
