"""多模态视觉接口：上传图片 → 推荐相似景点"""
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.services import vision_service
from app.services.knowledge_loader import city_name_to_code

router = APIRouter(prefix="/api/vision", tags=["vision"])

MAX_SIZE = 8 * 1024 * 1024  # 8MB


@router.post("/similar")
async def vision_similar(
    file: UploadFile = File(..., description="旅行照片/景点图片（jpg/png/webp）"),
    city: str = Form("", description="城市（中文名或代码），空表示全部城市"),
    top_k: int = Form(5, description="返回条数", ge=1, le=10),
):
    """上传照片，AI 分析图片内容并推荐相似景点（Chinese-CLIP 多模态）"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件（jpg/png/webp）")

    image_bytes = await file.read()
    if len(image_bytes) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="图片不能超过 8MB")
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="图片内容为空")

    try:
        results = vision_service.analyze_image(
            image_bytes,
            city=city_name_to_code(city) if city else None,
            top_k=top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {"image_name": file.filename, "total": len(results), "results": results}
