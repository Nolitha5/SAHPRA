import json
from pathlib import Path
import pytest
from m2.runtime import AppConfig,M2Runtime
from m2.cli import load_demo
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def demo(monkeypatch):
    monkeypatch.chdir(ROOT)
    cfg=AppConfig.from_file(ROOT/'config/default.json')
    runtime=M2Runtime(cfg)
    load_demo(runtime)
    return runtime
