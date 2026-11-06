"""Illustrate handoff to M3. RegulatoryChunk is separate from sponsor DossierChunk."""
import json
from pathlib import Path
from m2.schemas import DossierChunk
p=Path('examples/synthetic_s4_case.json')
doc=json.loads(p.read_text(encoding='utf-8'))
for item in doc['dossier_chunks']:
    DossierChunk.model_validate(item)
print(f"Validated {len(doc['dossier_chunks'])} M3-style dossier chunks; do not index them in regulatory RKB")
