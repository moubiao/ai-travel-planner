"""RAG 知识库检索接口：供调试与演示知识检索能力"""
from fastapi import APIRouter

from app.services import rag_service
from app.services.knowledge_loader import city_name_to_code
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/rag", tags=["rag"])


class RAGSearchRequest(BaseModel):
    """知识库检索请求"""

    query: str = Field(..., description="检索问题，如「成都 亲子 室内景点」")
    city: str = Field("", description="城市（中文名或代码），空表示全部城市")
    doc_type: str = Field("", description="文档类型：attraction / food / hotel，空表示全部")
    top_k: int = Field(10, description="返回条数", ge=1, le=30)


@router.post("/search")
def rag_search(req: RAGSearchRequest):
    """语义检索旅游知识库（BGE Embedding + FAISS + Rerank）"""
    doc_types = [req.doc_type] if req.doc_type else None
    results = rag_service.search(
        query=req.query,
        city=city_name_to_code(req.city) if req.city else None,
        doc_types=doc_types,
        top_k=req.top_k,
    )
    return {"query": req.query, "total": len(results), "results": results}
