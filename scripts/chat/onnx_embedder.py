"""Identical encode path for offline + runtime (the consistency anchor).
Uses onnxruntime; mean-pools + L2-normalizes; applies e5 prefixes."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

DEFAULT_DIR = Path("data/models/e5-small-onnx")


class OnnxEmbedder:
    def __init__(self, model_dir: Path = DEFAULT_DIR):
        self.session = ort.InferenceSession(str(model_dir / "model.onnx"),
                                             providers=["CPUExecutionProvider"])
        self.tok = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        self.model_id = (model_dir / "MODEL_ID.txt").read_text().strip()

    def _encode(self, texts: list[str]) -> np.ndarray:
        encs = [self.tok.encode(t) for t in texts]
        maxlen = max(len(e.ids) for e in encs)
        ids = np.zeros((len(encs), maxlen), dtype=np.int64)
        mask = np.zeros((len(encs), maxlen), dtype=np.int64)
        for i, e in enumerate(encs):
            ids[i, :len(e.ids)] = e.ids
            mask[i, :len(e.ids)] = e.attention_mask
        feeds = {"input_ids": ids, "attention_mask": mask}
        # token_type_ids if the graph needs it
        if any(i.name == "token_type_ids" for i in self.session.get_inputs()):
            feeds["token_type_ids"] = np.zeros_like(ids)
        out = self.session.run(None, feeds)[0]              # (n, seq, dim)
        m = mask[:, :, None].astype(np.float32)
        pooled = (out * m).sum(1) / np.clip(m.sum(1), 1e-9, None)  # mean-pool
        norm = np.linalg.norm(pooled, axis=1, keepdims=True)
        return (pooled / np.clip(norm, 1e-9, None)).astype(np.float32)

    def encode_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode([f"passage: {t}" for t in texts])

    def encode_query(self, text: str) -> np.ndarray:
        return self._encode([f"query: {text}"])[0]
