# Deployment and Operations
**Version:** 1.2 | **Date:** 2026-10-28

---

## 1. Prerequisites

- Python 3.10+ (tested on 3.13.2)
- Windows 10/11 or Linux
- ~100 MB disk (offline, hash-demo only)
- ~1.5 GB disk (with BGE models)

---

## 2. Installation

```powershell
cd "C:\Users\Staff 101\OneDrive\Desktop\SAHPRA_Member2_TokenSafe_CitationValidated_v1.1"

# Minimal (runs all tests without model downloads)
python -m pip install -e ".[dev]"

# Full (adds ChromaDB + BGE model support — downloads ~1.3 GB)
python -m pip install -e ".[dev,vector,models]"
```

---

## 3. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `M2_SERVICE_TOKEN` | Yes (research mode) | Bearer token for `/m2` API |
| `M2_PHINT_CATALOGUE` | Optional | Path to pharmacopoeial catalogue JSON |
| `HF_HOME` | Optional | Override Hugging Face cache (set to `PROJECT_ROOT/models/`) |
| `TRANSFORMERS_CACHE` | Optional | Override transformers model cache |

Recommended for offline containment:
```powershell
$env:HF_HOME = "C:\...\SAHPRA_Member2_TokenSafe_CitationValidated_v1.1\models"
$env:TRANSFORMERS_CACHE = "$env:HF_HOME"
```

---

## 4. Starting the REST Service

```powershell
$env:M2_SERVICE_TOKEN = "your-secret-token"
python -m uvicorn m2.api:router --host 127.0.0.1 --port 8001
```

Endpoints:
- `GET  /m2/health`
- `POST /m2/evidence`
- `POST /m2/s4/review`
- `POST /m2/phint/evidence`

---

## 5. Building the Real Vector Index

Only run after `pip install -e ".[vector,models]"` and on an internet-connected machine:

```powershell
python scripts/build_real_chroma_on_user_pc.py
```

This downloads BGE model weights to `models/` and creates a ChromaDB collection in `local_indexes/`.

---

## 6. Adding Pharmacopoeial Documents

1. Place the reviewed PDF in `pharmacopoeia/incoming/`
2. Calculate SHA-256: `python -c "from m2.registry import file_sha256; print(file_sha256('pharmacopoeia/incoming/file.pdf'))"`
3. Register the source:
```python
from m2.registry import SourceRegistry
from m2.schemas import SourceRecord, SourceType
from datetime import date

reg = SourceRegistry.load('local_indexes/registry.json')
reg.register(SourceRecord(
    source_id="PH-INT-VALSARTAN-2024",
    authority="WHO",
    title="International Pharmacopoeia — Valsartan",
    document_code="PH-INT-VALSARTAN",
    version="2024",
    effective_from=date(2024, 1, 1),
    source_type=SourceType.REGULATORY,
    approved=False,  # Set True only after human review
    sha256="<calculated hash>",
    provenance_verified=False   # Set True after verification
))
reg.save('local_indexes/registry.json')
```
4. After human review, set `approved=True` and `provenance_verified=True`.

---

## 7. Running Tests

```powershell
# All tests
python -m pytest tests/ -q

# With coverage (install pytest-cov separately)
python -m pytest tests/ --cov=m2 --cov-report=term-missing
```
