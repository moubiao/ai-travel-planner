"""RAG检索服务：BGE Embedding + FAISS 向量检索 + BGE Rerank 精排

流程：
1. 数据加载：knowledge/*.json → 文档列表（含 text 与 metadata）
2. 索引构建：BGE 向量化 → FAISS 内积索引 → 持久化到 data/faiss_index
3. 在线检索：向量召回 → 元数据过滤 → Rerank 精排 → top_k 结果
"""
import json
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import CrossEncoder, SentenceTransformer

from app.services.knowledge_loader import build_documents

# 模型目录：backend/models（用 download_models.py 从 ModelScope 下载）
MODELS_DIR = Path(__file__).resolve().parent.parent.parent / "models"
# Embedding 模型（中文语义向量，512维）—— 优先本地模型，缺失时回退 HuggingFace 在线
EMBEDDING_MODEL = str(MODELS_DIR / "bge-small-zh-v1.5") if (MODELS_DIR / "bge-small-zh-v1.5").exists() else "BAAI/bge-small-zh-v1.5"
# Rerank 模型（查询-文档相关性精排）
RERANK_MODEL = str(MODELS_DIR / "bge-reranker-base") if (MODELS_DIR / "bge-reranker-base").exists() else "BAAI/bge-reranker-base"
# 向量索引持久化目录：backend/data/faiss_index（本文件位于 backend/app/services/ 下）
INDEX_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "faiss_index"

_embedder = None
_reranker = None
_index = None
_documents = None


def get_embedder() -> SentenceTransformer:
    """懒加载 Embedding 模型（优先使用 GPU）"""
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder


def get_reranker() -> CrossEncoder:
    """懒加载 Rerank 模型"""
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(RERANK_MODEL)
    return _reranker


def build_index() -> tuple:
    """向量化全部文档并构建 FAISS 索引（数据更新后需重新调用）"""
    global _index, _documents
    documents = build_documents()
    texts = [doc["text"] for doc in documents]

    print(f"正在向量化 {len(texts)} 条知识文档...")
    vectors = get_embedder().encode(texts, normalize_embeddings=True, show_progress_bar=True)

    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(np.asarray(vectors, dtype=np.float32))

    # 持久化索引与文档（JSON 存储，避免 pickle 安全风险）
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(INDEX_DIR / "index.faiss"))
    with open(INDEX_DIR / "documents.json", "w", encoding="utf-8") as f:
        json.dump(documents, f, ensure_ascii=False, indent=2)

    _index, _documents = index, documents
    return index, documents


def load_index() -> tuple:
    """从本地加载索引（不存在则自动构建）"""
    global _index, _documents
    if _index is not None and _documents is not None:
        return _index, _documents

    index_file = INDEX_DIR / "index.faiss"
    doc_file = INDEX_DIR / "documents.json"
    if index_file.exists() and doc_file.exists():
        _index = faiss.read_index(str(index_file))
        with open(doc_file, "r", encoding="utf-8") as f:
            _documents = json.load(f)
    else:
        _index, _documents = build_index()
    return _index, _documents


def _metadata_match(doc: dict, filters: dict) -> bool:
    """判断文档是否满足过滤条件"""
    for key, value in filters.items():
        if value is None:
            continue
        if key == "city" and doc["city"] != value:
            return False
        if key == "type":
            # type 支持单个值或列表（如 ["attraction", "food"]）
            expected = value if isinstance(value, list) else [value]
            if doc["type"] not in expected:
                return False
        if key in ("indoor_outdoor", "category") and doc["metadata"].get(key) != value:
            return False
        if key == "max_ticket" and doc["metadata"].get("ticket", 0) > value:
            return False
        if key == "max_price" and doc["metadata"].get("price_per_person", doc["metadata"].get("price_per_night", 0)) > value:
            return False
    return True


def search(query: str, city: str | None = None, doc_types: list[str] | None = None,
           filters: dict | None = None, top_k: int = 10, fetch_k: int = 40,
           use_rerank: bool = True) -> list[dict]:
    """检索知识库：向量召回 → 元数据过滤 → Rerank 精排

    参数：
    - query: 检索问题，如「成都 亲子 室内景点」
    - city: 城市代码（chengdu / kunming），None 表示全部城市
    - doc_types: 文档类型过滤，如 ["attraction", "food"]
    - filters: 额外元数据过滤，如 {"indoor_outdoor": "indoor"}
    - top_k: 返回条数
    - fetch_k: 向量召回条数（先多召回再精排）
    - use_rerank: 是否使用 Rerank 精排
    """
    index, documents = load_index()

    # 1. 向量召回
    query_vec = get_embedder().encode([query], normalize_embeddings=True)
    scores, indices = index.search(np.asarray(query_vec, dtype=np.float32), fetch_k)

    # 2. 元数据过滤
    filters = filters or {}
    if city:
        filters["city"] = city
    if doc_types:
        filters["type"] = doc_types  # type 支持列表
    candidates = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        doc = documents[idx]
        if not _metadata_match(doc, filters):
            continue
        candidates.append({
            "id": doc["id"],
            "type": doc["type"],
            "city": doc["city"],
            "city_name": doc["city_name"],
            "name": doc["name"],
            "text": doc["text"],
            "metadata": doc["metadata"],
            "score": float(score),
        })

    if not candidates:
        return []

    # 3. Rerank 精排（查询与候选两两打分）
    if use_rerank and len(candidates) > 1:
        pairs = [[query, c["text"]] for c in candidates]
        rerank_scores = get_reranker().predict(pairs)
        for c, s in zip(candidates, rerank_scores):
            c["score"] = float(s)
        candidates.sort(key=lambda x: x["score"], reverse=True)

    return candidates[:top_k]


def search_for_requirement(structured: dict) -> dict:
    """根据结构化旅行需求检索知识资料（支持多城市）

    返回：{"attractions": [...], "foods": [...], "hotels": [...], "city": 城市代码, "city_name": "城市名"}
    多城市时 attractions 等为各城市检索结果合并，city_name 用「成都+重庆」表示
    """
    destination = structured.get("destination", "")
    preferences = structured.get("preferences", []) or []
    special = structured.get("special_requirements", "") or ""
    budget = structured.get("budget", 0) or 0

    from app.services.knowledge_loader import city_name_to_code, resolve_cities
    # 多城市解析：cities 字段优先，否则从 destination 解析（含别名/组合）
    cities = resolve_cities(structured.get("cities") or destination)
    if not cities:
        cities = resolve_cities(destination)

    pref_str = " ".join(preferences) if preferences else "热门推荐"

    # 过滤条件：按偏好标签粗筛、按预算过滤门票/人均价
    filters = {}
    if budget and budget < 1500:
        filters["max_ticket"] = 80  # 低预算时优先免票/低价景点

    all_attractions, all_foods, all_hotels = [], [], []
    for city_name in cities:
        city = city_name_to_code(city_name)
        if not city:
            continue
        all_attractions += search(
            query=f"{city_name} {pref_str} 景点 游玩推荐",
            city=city, doc_types=["attraction"], filters=filters,
            top_k=10,
        )
        all_foods += search(
            query=f"{city_name} {pref_str} 美食 餐厅推荐",
            city=city, doc_types=["food"], filters=filters,
            top_k=6,
        )
        all_hotels += search(
            query=f"{city_name} 住宿 酒店推荐",
            city=city, doc_types=["hotel"],
            top_k=3,
        )

    return {
        "attractions": all_attractions,
        "foods": all_foods,
        "hotels": all_hotels,
        "city": "+".join(city_name_to_code(c) or "" for c in cities),
        "city_name": "+".join(cities) if cities else destination,
    }


def format_knowledge_for_prompt(knowledge: dict) -> str:
    """将检索结果格式化为 Prompt 注入文本"""
    lines = []
    for att in knowledge["attractions"]:
        m = att["metadata"]
        lines.append(
            f"【景点 {att['id']}】{att['name']} | 类别:{m.get('category','')} "
            f"| 门票:{m.get('ticket',0)}元 | 位置:{m.get('location','')} | "
            f"标签:{'/'.join(m.get('tags',[]))} | {att['text'].split('。')[0:3] and '。'.join(att['text'].split('。')[:3])}"
        )
    for food in knowledge["foods"]:
        lines.append(
            f"【美食 {food['id']}】{food['name']} | 类别:{food['metadata'].get('category','')} "
            f"| 人均:{food['metadata'].get('price_per_person',0)}元 | 区域:{food['metadata'].get('area','')}"
        )
    for hotel in knowledge["hotels"]:
        lines.append(
            f"【酒店 {hotel['id']}】{hotel['name']} | 每晚:{hotel['metadata'].get('price_per_night',0)}元 "
            f"| 星级:{hotel['metadata'].get('stars','')} | 区域:{hotel['metadata'].get('area','')}"
        )
    return "\n".join(lines)


def build_references(plan: dict, knowledge: dict) -> list[dict]:
    """从方案中收集引用的知识库来源（按 source_id 去重）"""
    source_map = {
        doc["id"]: doc
        for doc in knowledge["attractions"] + knowledge["foods"] + knowledge["hotels"]
    }
    used_ids = set()
    for day in plan.get("daily_schedule", []):
        for slot in ("morning", "afternoon", "evening"):
            sid = day.get(slot, {}).get("source_id") if isinstance(day.get(slot), dict) else None
            if sid:
                used_ids.add(sid)
    for food in plan.get("food_recommendations", []):
        if food.get("source_id"):
            used_ids.add(food["source_id"])
    hotel = plan.get("hotel_recommendation", {}) or {}
    if hotel.get("source_id"):
        used_ids.add(hotel["source_id"])

    references = []
    for sid in used_ids:
        doc = source_map.get(sid)
        if doc:
            ref = {
                "id": doc["id"],
                "name": doc["name"],
                "type": doc["type"],
                "city_name": doc["city_name"],
                "source": doc["metadata"].get("source", ""),
                "verified_at": doc["metadata"].get("verified_at", ""),
            }
            # 景点附带坐标（前端地图渲染用）
            if doc["type"] == "attraction":
                ref["coordinates"] = doc["metadata"].get("coordinates", [])
            references.append(ref)
    return references
