"""Nonclinical catalogue demo; no WHO monograph PDFs included or compliance claims."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from m2.pharmacopoeia import PharmacopoeiaCatalogue
from m2.pharmacopoeia_service import lookup_compendial_evidence
from m2.registry import SourceRegistry
from m2.embeddings import HashEmbedder
from m2.storage import MemoryVectorStore
from m2.retrieval import EvidenceService
c=PharmacopoeiaCatalogue.load(ROOT/'pharmacopoeia/WHO_PHINT_RESEARCH_CATALOGUE_v0.7.json')
s=EvidenceService(MemoryVectorStore(HashEmbedder()),SourceRegistry())
print(json.dumps(lookup_compendial_evidence(c,s,substance='Paracetamol',cas='103-90-2',
            question='What monograph information concerns identity and assay?',
            requesting_agent='S4_CONTROL'),indent=2))
