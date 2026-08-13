"""从 ModelScope（魔搭）下载 BGE 模型到本地目录

国内网络环境替代 HuggingFace 下载方案：
    python download_models.py
模型保存位置：backend/models/bge-small-zh-v1.5 和 backend/models/bge-reranker-base
"""
import os
from pathlib import Path

# 绕过异常的 Windows 系统代理（代理服务未运行时 pip/下载会失败）
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

MODELS_DIR = Path(__file__).resolve().parent / "models"

# (魔搭模型ID, 本地目录名)
MODELS = [
    ("BAAI/bge-small-zh-v1.5", "bge-small-zh-v1.5"),
    ("BAAI/bge-reranker-base", "bge-reranker-base"),
    ("AI-ModelScope/chinese-clip-vit-base-patch16", "chinese-clip-vit-base-patch16"),
]


def main():
    from modelscope import snapshot_download

    for model_id, local_name in MODELS:
        target = MODELS_DIR / local_name
        print(f"==> 下载 {model_id} -> {target}")
        snapshot_download(
            model_id,
            local_dir=str(target),
            allow_patterns=["*.json", "*.txt", "*.safetensors", "*.py", "*.md"],
        )
        print(f"==> {local_name} 完成")


if __name__ == "__main__":
    main()
