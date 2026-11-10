# Agentic QA-RAG · Member 2 — Retrieval & Knowledge Base

**SAHPRA Module 3.2.S** · Agents: **Evidence/RERA** and **S.4 Control**

> Research-support component. It finds and cites regulatory passages and runs rule-based checks.
> It never decides that a dossier is compliant: every finding is marked for review, and the qualified
> human SAHPRA assessor makes every final decision.

This folder holds two parts:

| Part | Folder | What it is |
|---|---|---|
| **Backend** | [`member2-rag/`](member2-rag/) | Python: ChromaDB knowledge base, BGE embeddings + reranker, the shared retrieval service, both agents, benchmarks, and a FastAPI server |
| **Dashboard** | [`src/`](src/) (this folder) | React + Vite web UI that talks to the backend's `/api` |

**All backend documentation** — architecture, loading passages, agents, benchmarks, team integration,
security — is in **[`member2-rag/README.md`](member2-rag/README.md)**. The ICH pilot walkthrough is in
[`member2-rag/docs/ICH_PILOT.md`](member2-rag/docs/ICH_PILOT.md).

## Quick start

You need **Python 3.12 or 3.13** and **Node.js 18+**.

### 1. Install (first time)

```powershell
cd member2-rag
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
copy .env.example .env
cd ..
npm install
```

### 2. Build the knowledge base (first time)

The guideline PDFs and the vector database are not in the repository. One command downloads the 16
public ICH, WHO and SAHPRA guidelines from their official sites (listed in
`member2-rag/sources/kb_v2_manifest.json`), converts them and indexes them:

```powershell
cd member2-rag
.\.venv\Scripts\Activate.ps1
python scripts/build_knowledge_base.py
```

This takes about 10–20 minutes on a CPU. The first run also downloads the embedding and reranker models
from Hugging Face (~2.4 GB; see `member2-rag/README.md` §5 for smaller options). Running it again only
fetches what is missing. Once it has worked, uncomment `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`
in `member2-rag/.env`; otherwise a slow connection can make searches hang.

### 3. Run (development)

Two terminals:

```powershell
# Terminal 1 — API on http://127.0.0.1:8000 (interactive docs at /api/docs)
cd member2-rag
.\.venv\Scripts\Activate.ps1
python -m app.api
```

```powershell
# Terminal 2 — dashboard on http://localhost:5173
npm run dev
```

Vite forwards `/api` requests to the Python server, so the browser never needs the API address or any key.
If port 8000 is already taken on your computer (for example by Docker), set `M2_API_PORT=8010` in
`member2-rag/.env`; `npm run dev` picks up the same port automatically.

### 4. Run (single server)

```powershell
npm run build                # typecheck + build into dist/
cd member2-rag
python -m app.api            # serves the API and the built dashboard at http://127.0.0.1:8000
```

## Dashboard tabs

| Tab | Purpose |
|---|---|
| **Knowledge Base** | The one knowledge base that Search and the agents use: which guidelines are indexed or missing, passages and pages per source, coverage of each CTD 3.2.S heading; then browse and filter every passage, import JSONL (dry-run or index), delete passages |
| **Search** | Just type a question. The app searches all 16 guidelines, works out the CTD section from where the best-matching passages come from, and sends the question to the right agent: 3.2.S.4 topics to **S.4 Control**, everything else to **Evidence/RERA**. It shows which agent and section it chose and why. The result is a cited finding in Word-style tables (QA status, conclusion, citations with printed and PDF page numbers and search scores, the tables found on the cited pages with an image of the original, supporting passages) with a red assessor-review box, downloadable as a Word report. *Advanced options* let you pick the CTD section (structured ICH M4Q headings) or agent yourself |
| **Benchmark** | Manage expert benchmark questions and view `results/retrieval_benchmark_*.json` summaries |

## Editing (import, delete, benchmark changes)

Editing is **off** unless `M2_ADMIN_TOKEN` (at least 12 characters) is set in `member2-rag/.env`. Restart
the API after changing it, then click **Unlock editing** in the dashboard and enter the same token. The
token is kept only in that browser tab (sessionStorage) and sent in the `X-Admin-Token` header.

The API listens on `127.0.0.1` only by default. Do not change `M2_API_HOST` to `0.0.0.0` unless you know
who else can reach the machine.

## Frontend scripts

| Command | Does |
|---|---|
| `npm run dev` | Dev server on port 5173 with `/api` proxy |
| `npm run lint` | ESLint (TypeScript + React hooks rules) |
| `npm run typecheck` | `tsc --noEmit` |
| `npm test` | Vitest unit tests (`src/**/*.test.ts`) |
| `npm run check` | Lint + typecheck + tests in one go |
| `npm run build` | Typecheck, then build into `dist/` |
| `npm run preview` | Preview the built bundle (needs the API running for data) |

## Checks before you push

```powershell
npm run check                                   # dashboard
cd member2-rag; python -m ruff check; python -m pytest   # backend (pip install -r requirements-dev.txt once)
```

The same checks run automatically on GitHub for every push and pull request
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)). They need no secrets and download no models.

## Never commit

`.env`, `member2-rag/data/` (ChromaDB, processed passages, source PDFs), `member2-rag/results/`, sponsor
dossiers, `node_modules/`, `dist/`. The `.gitignore` files block these.

## Word reports

Click **Download Word document** above the search results to save a `.docx` report. Nothing is
downloaded automatically. Assessor comments saved on a finding appear in red in the report. Reports are built in
the browser, and assessor comments are saved only in that browser (`localStorage`): neither is sent to the server.
