"""阶段二验收测试：RAG 检索质量抽查"""
from app.services import rag_service

TEST_CASES = [
    ("成都 亲子 室内景点 博物馆", "chengdu", ["attraction"], "成都室内亲子景点"),
    ("昆明 冬季 红嘴鸥 观鸥", "kunming", ["attraction"], "昆明观鸥景点"),
    ("成都 火锅 聚餐", "chengdu", ["food"], "成都火锅"),
    ("昆明 过桥米线 老字号", "kunming", ["food"], "昆明米线"),
    ("昆明 翠湖 附近 住宿", "kunming", ["hotel"], "昆明翠湖酒店"),
]

print("=" * 60)
for query, city, doc_types, desc in TEST_CASES:
    print(f"\n【{desc}】query: {query} | city: {city}")
    results = rag_service.search(query, city=city, doc_types=doc_types, top_k=3)
    for i, r in enumerate(results, 1):
        print(f"  {i}. [{r['type']}] {r['name']} (score={r['score']:.3f})")
    if not results:
        print("  （无结果）")

# 过滤验证：室内景点
print("\n【室内过滤】成都 indoor_outdoor=indoor")
results = rag_service.search("成都 景点", city="chengdu", doc_types=["attraction"],
                             filters={"indoor_outdoor": "indoor"}, top_k=5)
for i, r in enumerate(results, 1):
    print(f"  {i}. [{r['metadata']['indoor_outdoor']}] {r['name']}")

# 跨城市隔离验证：查昆明不应出现成都景点
print("\n【跨城市隔离】昆明检索中检查是否混入成都文档")
results = rag_service.search("成都 熊猫 宽窄巷子", city="kunming", top_k=5)
bad = [r for r in results if r["city"] != "kunming"]
print(f"  结果数: {len(results)}, 非昆明文档数: {len(bad)}")
for r in results:
    print(f"  - [{r['city']}] {r['name']}")

print("\n检索测试完成")
