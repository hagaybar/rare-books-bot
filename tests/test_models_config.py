import json
import tempfile
from pathlib import Path

import pytest

from scripts.models.config import ModelConfig, load_config, get_model


def test_load_config_from_file(tmp_path):
    """Config loads from JSON file."""
    config_file = tmp_path / "model-config.json"
    config_file.write_text(json.dumps({
        "interpreter": {"model": "gpt-4.1-mini"},
        "narrator": {"model": "gpt-5-mini"},
        "meta_extraction": {"model": "gpt-4.1-nano"},
        "judge": {"model": "gpt-4.1"},
    }))
    cfg = load_config(config_file)
    assert cfg.interpreter.model == "gpt-4.1-mini"
    assert cfg.narrator.model == "gpt-5-mini"
    assert cfg.meta_extraction.model == "gpt-4.1-nano"
    assert cfg.judge.model == "gpt-4.1"


def test_load_config_defaults_when_missing():
    """Config returns defaults when file doesn't exist."""
    cfg = load_config(Path("/nonexistent/config.json"))
    assert cfg.interpreter.model == "gpt-4.1-mini"
    assert cfg.narrator.model == "gpt-4.1"
    assert cfg.meta_extraction.model == "gpt-4.1-nano"
    assert cfg.judge.model == "gpt-4.1"


def test_get_model_returns_stage_model(tmp_path):
    """get_model() returns the model string for a stage."""
    config_file = tmp_path / "model-config.json"
    config_file.write_text(json.dumps({
        "interpreter": {"model": "gpt-5-mini"},
        "narrator": {"model": "gpt-4.1"},
        "meta_extraction": {"model": "gpt-4.1-nano"},
        "judge": {"model": "gpt-4.1"},
    }))
    cfg = load_config(config_file)
    assert get_model(cfg, "interpreter") == "gpt-5-mini"
    assert get_model(cfg, "narrator") == "gpt-4.1"


def test_get_model_unknown_stage_raises():
    """get_model() raises for unknown stage."""
    cfg = load_config(Path("/nonexistent"))
    with pytest.raises(KeyError):
        get_model(cfg, "nonexistent_stage")
