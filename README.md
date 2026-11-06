# SAHPRA Agentic QA-RAG

This is the team repository for the SAHPRA Agentic QA-RAG research project — a multi-agent system designed to assist regulatory assessment of pharmaceutical manufacturing dossiers.

> **Research prototype only.** This system does not independently authorise or reject medicines. All outputs require review by a qualified human assessor.

## Repository Structure

| Folder | Description |
|---|---|
| [`member2/`](member2/README.md) | Member 2 — Regulatory Knowledge Base and Evidence Retrieval (Aziz & Sipho) |
| [`Merged Member2/`](Merged%20Member2/README.md) | Member 2 application: React assessor dashboard (Knowledge Base, Coverage, Search, Agents, Benchmark; Word reports; assessor review) and FastAPI backend, with the knowledge base rebuilt from the `member2/` regulatory source list (16 public ICH/WHO/SAHPRA guidelines) |

## About the Project

The SAHPRA Agentic QA-RAG system assists assessors reviewing CTD Module 3 pharmaceutical manufacturing dossiers by:

1. Ingesting and structuring dossier sections (Member 1)
2. Retrieving relevant regulatory evidence from ICH/WHO/EMA guidances (Member 2)
3. Identifying gaps and deficiencies (Member 3)
4. Generating draft assessment reports (Member 4)
5. Supporting human assessor review (Member 5)

This repository is the shared workspace for all team members.
