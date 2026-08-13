"""视觉服务：Chinese-CLIP 图片理解 → 推荐相似景点（多模态能力）

用户上传旅行照片/景点图片，模型提取图片语义特征，与知识库景点文本特征
计算相似度，推荐风格相近的地点。全本地运行（无外部 API 依赖）。
"""
import io
from pathlib import Path

import torch
from PIL import Image

from app.services.knowledge_loader import build_documents

# Chinese-CLIP 模型目录（backend/models/，用 download_models.py 从 ModelScope 下载）
MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "chinese-clip-vit-base-patch16"

_image_processor = None
_tokenizer = None
_model = None
_device = None


def _load():
    """懒加载 CLIP 模型、图像处理器与中文分词器"""
    global _image_processor, _tokenizer, _model, _device
    if _model is not None:
        return

    if not MODEL_DIR.exists():
        raise RuntimeError("Chinese-CLIP 模型未下载，请先运行: python download_models.py 或手动下载到 backend/models/chinese-clip-vit-base-patch16")

    from transformers import BertTokenizer, CLIPImageProcessor, ChineseCLIPModel

    _device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[vision] 加载 Chinese-CLIP 模型（{_device}）...")
    # Chinese-CLIP 专用模型类（文本编码器为中文 BERT 架构）
    _model = ChineseCLIPModel.from_pretrained(str(MODEL_DIR)).to(_device)
    _model.eval()
    # 图像处理：标准 CLIP 预处理（模型目录的 preprocessor_config.json）
    _image_processor = CLIPImageProcessor.from_pretrained(str(MODEL_DIR))
    # 中文分词：Chinese-CLIP 使用中文 BERT 词表（vocab.txt）
    _tokenizer = BertTokenizer.from_pretrained(str(MODEL_DIR))
    print("[vision] 模型加载完成")


def _get_image_features(image_tensor):
    """获取图像特征（兼容 transformers 5.x 返回值变化）"""
    features = _model.get_image_features(**image_tensor)
    # transformers 5.x 可能返回 BaseModelOutputWithPooling 而非 tensor
    if hasattr(features, "pooler_output"):
        features = features.pooler_output
    return features


def _get_text_features(text_tensor):
    """获取文本特征（兼容 transformers 5.x 返回值变化）"""
    features = _model.get_text_features(**text_tensor)
    if hasattr(features, "pooler_output"):
        features = features.pooler_output
    return features


def analyze_image(image_bytes: bytes, city: str | None = None, top_k: int = 5) -> list[dict]:
    """分析图片，推荐相似景点

    参数：
    - image_bytes: 图片二进制内容
    - city: 城市代码过滤（None 表示全部城市）
    - top_k: 返回条数

    返回：[{id, name, city_name, score, description}]
    """
    _load()

    # 1. 候选景点文档（可选城市过滤）
    documents = build_documents()
    candidates = [doc for doc in documents if doc["type"] == "attraction"]
    if city:
        candidates = [doc for doc in candidates if doc["city"] == city]
    if not candidates:
        return []

    # 2. 图片特征
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise ValueError(f"无法解析图片: {exc}")
    inputs = _image_processor(images=image, return_tensors="pt").to(_device)
    with torch.no_grad():
        image_features = _get_image_features(inputs)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        # 3. 景点文本特征（中文分词，分批处理避免显存溢出）
        texts = [doc["text"] for doc in candidates]
        text_features_list = []
        batch_size = 32
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            text_inputs = _tokenizer(batch_texts, padding=True, truncation=True, return_tensors="pt").to(_device)
            with torch.no_grad():
                batch_features = _get_text_features(text_inputs)
                batch_features = batch_features / batch_features.norm(dim=-1, keepdim=True)
                text_features_list.append(batch_features)
        text_features = torch.cat(text_features_list, dim=0)

        # 4. 相似度排序
        scores = (image_features @ text_features.T).squeeze(0)
        top_indices = scores.topk(min(top_k, len(candidates))).indices.tolist()

    results = []
    for idx in top_indices:
        doc = candidates[idx]
        results.append({
            "id": doc["id"],
            "name": doc["name"],
            "city_name": doc["city_name"],
            "score": round(float(scores[idx]), 4),
            "description": doc["text"].split("。")[2] if len(doc["text"].split("。")) > 2 else doc["text"][:60],
        })
    return results
