"""阶段五验收测试：多模态图片理解（Chinese-CLIP）

用 Pillow 生成测试图片，验证：
1. 自然风景图 → 推荐自然风光类景点
2. 城市街景图 → 推荐城市休闲类景点
"""
import io

from PIL import Image, ImageDraw

from app.services import vision_service


def make_nature_image() -> bytes:
    """生成自然风景测试图：蓝天 + 绿色山丘"""
    img = Image.new("RGB", (224, 224), (135, 206, 235))  # 天空蓝
    draw = ImageDraw.Draw(img)
    draw.ellipse([-50, 120, 280, 350], fill=(34, 139, 34))  # 绿色山丘
    draw.ellipse([-80, 150, 300, 400], fill=(60, 179, 113))  # 深绿山丘
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_city_image() -> bytes:
    """生成城市街景测试图：灰色建筑 + 街道"""
    img = Image.new("RGB", (224, 224), (180, 180, 185))  # 城市灰
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 40, 90, 220], fill=(105, 105, 110))  # 建筑1
    draw.rectangle([100, 80, 170, 220], fill=(90, 90, 95))  # 建筑2
    draw.rectangle([180, 60, 250, 220], fill=(100, 100, 105))  # 建筑3
    draw.rectangle([0, 200, 224, 224], fill=(70, 70, 75))  # 街道
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_nature_image():
    """自然风景图应推荐自然风光/户外类景点"""
    print("=== 自然风景图测试 ===")
    results = vision_service.analyze_image(make_nature_image(), top_k=5)
    assert results, "无推荐结果"
    for i, r in enumerate(results, 1):
        print(f"  {i}. [{r['city_name']}] {r['name']} (相似度={r['score']})")
    names = [r["name"] for r in results]
    nature_keywords = ["雪山", "公园", "湿地", "森林", "山", "湖", "坝", "景区"]
    hit = any(any(k in n for k in nature_keywords) for n in names)
    print(f"自然类推荐命中: {hit}")
    assert hit, "自然风景图未推荐到自然类景点"
    print("自然风景图测试通过 ✓")


def test_city_image():
    """城市街景图应推荐城市休闲/地标类景点"""
    print("\n=== 城市街景图测试 ===")
    results = vision_service.analyze_image(make_city_image(), top_k=5)
    assert results, "无推荐结果"
    for i, r in enumerate(results, 1):
        print(f"  {i}. [{r['city_name']}] {r['name']} (相似度={r['score']})")
    names = [r["name"] for r in results]
    city_keywords = ["广场", "街", "坊", "塔", "楼", "寺", "馆", "公园"]
    hit = any(any(k in n for k in city_keywords) for n in names)
    print(f"城市类推荐命中: {hit}")
    assert hit, "城市街景图未推荐到城市类景点"
    print("城市街景图测试通过 ✓")


if __name__ == "__main__":
    test_nature_image()
    test_city_image()
    print("\n多模态视觉测试通过！")
