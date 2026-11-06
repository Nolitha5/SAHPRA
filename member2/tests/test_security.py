import os
from fastapi import FastAPI
from fastapi.testclient import TestClient
from m2.api import router,set_runtime
from m2.runtime import M2Runtime,AppConfig
from m2.schemas import SourceRecord,SourceType,RegulatoryChunk


def test_research_api_requires_token(monkeypatch):
    # Use production-compatible test embedder via constructed demo runtime, with config mode
    # switched after creation strictly for the auth gate (not a valid prod runtime).
    from m2.runtime import AppConfig
    demo=M2Runtime(AppConfig(mode='demo',backend='memory'))
    demo.cfg.mode='research'
    set_runtime(demo)
    app=FastAPI();app.include_router(router);client=TestClient(app)
    monkeypatch.delenv('M2_SERVICE_TOKEN',raising=False)
    assert client.get('/m2/health').status_code==503
    monkeypatch.setenv('M2_SERVICE_TOKEN','demo-secret-only')
    assert client.get('/m2/health').status_code==401
    assert client.get('/m2/health',headers={'X-M2-Token':'bad'}).status_code==401
    assert client.get('/m2/health',headers={'X-M2-Token':'demo-secret-only'}).status_code==200
