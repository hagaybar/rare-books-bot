"""Export intfloat/multilingual-e5-small to ONNX + tokenizer (pinned).
Run offline (GPU or CPU). Writes data/models/e5-small-onnx/.

The heavy ``optimum``/``transformers`` imports live INSIDE ``main()`` so this
module imports cleanly in the project venv (which does not ship optimum); the
export itself is run by the orchestrator in a scratch venv.
"""
from pathlib import Path

MODEL_ID = "intfloat/multilingual-e5-small"
OUT = Path("data/models/e5-small-onnx")


def main():
    from optimum.onnxruntime import ORTModelForFeatureExtraction
    from transformers import AutoTokenizer

    OUT.mkdir(parents=True, exist_ok=True)
    m = ORTModelForFeatureExtraction.from_pretrained(MODEL_ID, export=True)
    m.save_pretrained(OUT)
    AutoTokenizer.from_pretrained(MODEL_ID).save_pretrained(OUT)
    (OUT / "MODEL_ID.txt").write_text(MODEL_ID + "\n")
    print("exported to", OUT)


if __name__ == "__main__":
    main()
