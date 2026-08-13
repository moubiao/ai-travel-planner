"""构建 RAG 向量索引：加载知识库 → BGE 向量化 → FAISS 持久化

用法（在 backend 目录下）：
    python build_index.py
知识库数据更新后重新运行本脚本即可重建索引。
"""
from app.services.rag_service import build_index

if __name__ == "__main__":
    index, documents = build_index()
    print(f"索引构建完成：{len(documents)} 条文档，向量维度 {index.d}")
