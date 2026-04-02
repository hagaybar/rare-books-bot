"""Stage-to-model configuration.

Loads model assignments from a JSON config file. Falls back to defaults
if the file is missing. Each pipeline stage (interpreter, narrator, etc.)
maps to a model string compatible with litellm (e.g., "gpt-4.1",
"anthropic/claude-sonnet-4-6", "ollama/llama3").
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path("data/eval/model-config.json")


@dataclass
class StageConfig:
    """Configuration for a single pipeline stage."""
    model: str


@dataclass
class ModelConfig:
    """Full model configuration across all pipeline stages."""
    interpreter: StageConfig = field(default_factory=lambda: StageConfig(model="gpt-4.1"))
    narrator: StageConfig = field(default_factory=lambda: StageConfig(model="gpt-4.1"))
    meta_extraction: StageConfig = field(default_factory=lambda: StageConfig(model="gpt-4.1-nano"))
    judge: StageConfig = field(default_factory=lambda: StageConfig(model="gpt-4.1"))


def load_config(path: Optional[Path] = None) -> ModelConfig:
    """Load model config from JSON file, falling back to defaults."""
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        logger.info("Model config not found at %s — using defaults", config_path)
        return ModelConfig()

    try:
        raw = json.loads(config_path.read_text())
        return ModelConfig(
            interpreter=StageConfig(model=raw.get("interpreter", {}).get("model", "gpt-4.1")),
            narrator=StageConfig(model=raw.get("narrator", {}).get("model", "gpt-4.1")),
            meta_extraction=StageConfig(model=raw.get("meta_extraction", {}).get("model", "gpt-4.1-nano")),
            judge=StageConfig(model=raw.get("judge", {}).get("model", "gpt-4.1")),
        )
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to parse model config at %s: %s — using defaults", config_path, e)
        return ModelConfig()


def get_model(config: ModelConfig, stage: str) -> str:
    """Get the model string for a pipeline stage.

    Raises KeyError if stage is not a known field of ModelConfig.
    """
    try:
        stage_config: StageConfig = getattr(config, stage)
    except AttributeError:
        raise KeyError(f"Unknown pipeline stage: {stage}")
    return stage_config.model
