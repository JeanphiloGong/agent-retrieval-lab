"""Pinned local ONNX models. Errors propagate; no lexical fallback is disguised as a model."""
from pathlib import Path

from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder
from fastembed.common.model_description import ModelSource, PoolingType
from huggingface_hub import snapshot_download


EMBEDDING = ("sentence-transformers/all-MiniLM-L6-v2", "1110a243fdf4706b3f48f1d95db1a4f5529b4d41")
RERANKER = ("Xenova/ms-marco-MiniLM-L-6-v2", "a09144355adeed5f58c8ed011d209bf8ee5a1fec")


def download(model: tuple[str, str], cache: Path) -> str:
    return snapshot_download(model[0], revision=model[1], cache_dir=str(cache), allow_patterns=[
        "config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json",
        "vocab.txt", "sentence_bert_config.json", "1_Pooling/config.json", "onnx/model.onnx",
    ])


def load_embedding(cache: Path):
    path = download(EMBEDDING, cache)
    name = "lab/all-MiniLM-L6-v2-pinned"
    if not any(model["model"] == name for model in TextEmbedding.list_supported_models()):
        TextEmbedding.add_custom_model(name, pooling=PoolingType.MEAN, normalization=True,
            sources=ModelSource(hf=EMBEDDING[0]), dim=384, model_file="onnx/model.onnx")
    return TextEmbedding(name, threads=2, specific_model_path=path)


def load_reranker(cache: Path):
    path = download(RERANKER, cache)
    return TextCrossEncoder(RERANKER[0], threads=2, specific_model_path=path)
