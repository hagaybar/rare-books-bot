#!/usr/bin/env bash
# Orchestrator artifact build for semantic subject search (#63).
# Exports e5-small -> data/models/e5-small-onnx (scratch venv w/ optimum) and embeds
# the distinct subject headings -> subject_embeddings (project venv w/ onnxruntime),
# then runs a consistency sanity-check. Run from project root. Not part of the app.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
SCRATCH=/tmp/sss_build

echo "== 1. scratch venv (optimum export) =="
if [ ! -x "$SCRATCH/bin/python" ]; then
  python3 -m venv "$SCRATCH"
  "$SCRATCH/bin/pip" -q install --upgrade pip
  "$SCRATCH/bin/pip" -q install "optimum[onnxruntime]" transformers torch \
      --extra-index-url https://download.pytorch.org/whl/cpu
fi

echo "== 2. export model -> data/models/e5-small-onnx =="
"$SCRATCH/bin/python" scripts/index/export_embed_model.py
ls -la data/models/e5-small-onnx/ | sed -n '1,12p'

echo "== 3. embed headings -> subject_embeddings (project venv) =="
PYTHONPATH=. poetry run python scripts/index/embed_subjects.py

echo "== 4. consistency sanity-check (OnnxEmbedder must reproduce sane cosine) =="
PYTHONPATH=. poetry run python - <<'PY'
import numpy as np
from scripts.chat.onnx_embedder import OnnxEmbedder
e = OnnxEmbedder()
q = e.encode_query("philosophy")
p = e.encode_passages(["Philosophy", "Jewish liturgy -- Texts"])
cos_phil = float(p[0] @ q)
cos_litur = float(p[1] @ q)
print(f"cos(query 'philosophy', passage 'Philosophy')      = {cos_phil:.3f}")
print(f"cos(query 'philosophy', passage 'Jewish liturgy')  = {cos_litur:.3f}")
assert cos_phil > 0.85, f"ONNX encode looks wrong: {cos_phil} (prototype was ~0.905)"
assert cos_phil > cos_litur + 0.05, "philosophy must rank above an unrelated heading"
print("SANITY OK")
PY

echo "ARTIFACT_BUILD_OK"
