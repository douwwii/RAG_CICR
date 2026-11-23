"""Téléchargement local de révisions officielles ; aucun modèle installé sur wired."""
import os
os.environ.setdefault('HF_HUB_DISABLE_XET','1')
from huggingface_hub import snapshot_download

for model, revision in [
    ('BAAI/bge-m3','5617a9f61b028005a4858fdac845db406aefb181'),
    ('Qwen/Qwen3-Embedding-0.6B','97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3'),
]:
    print(snapshot_download(model, revision=revision,
        allow_patterns=['*.json','*.txt','*.model','*.safetensors','pytorch_model.bin','1_Pooling/*'],
        ignore_patterns=['onnx/*','openvino/*'], max_workers=2),flush=True)
