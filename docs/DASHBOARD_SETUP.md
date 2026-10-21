# Integrated dashboard

The maintained dashboard lives in `frontend/`. Vite builds the React app into `api/static/`; Flask serves the built index at `/` and its assets under `/static/`. This lets a user access the UI and the API from one local application origin.

## Local run

1. Start Exasol Personal using the existing supported launcher if needed.
2. Confirm `api/.env` is configured for the dedicated read-only `OPSNEXUS_API` identity and validated TLS. Do not copy credentials from the Logesh project; its local legacy backend was configured for SYS and is not part of this integrated application.
3. From the repository root, run:

   ```powershell
   & '.\synthetic-data\.venv\Scripts\python.exe' -m flask --app api.app run --host 127.0.0.1 --port 5000
   ```

4. Open <http://127.0.0.1:5000/>. The page reports Exasol health and renders findings from `OPS_INTEL.V_FINDINGS` through the read-only API.

To rebuild after frontend edits:

```powershell
cd frontend
npm install
npm run build
cd ..
```

For hot reload, use `npm run dev` from `frontend/`; Vite proxies `/api` and `/health` to Flask at `127.0.0.1:5000`. The dev server is separate by design; the production build served through Flask is the single-application experience.

## Current feature boundary

The integrated UI uses `GET /health`, `GET /api/findings`, and `GET /api/findings/<finding_id>`. It supports type and severity filters, page navigation, search within the current page, and a finding detail panel. Evidence, source references, and recommended actions come from the API without presenting a signal as a confirmed root cause. `POST /api/rag/query` selects the most relevant single finding from the curated Exasol view for the local CPU-bound Ollama model; the assistant uses only that evidence and does not generate or execute SQL. Set `OLLAMA_URL` to a loopback endpoint and `OLLAMA_MODEL` to an installed local model in `api/.env`. Missing or unreachable models return a sanitized `503`.

Logesh's supplied dashboard lives in `exasol-dashboard/`. Its `Intelligence Findings` page reads the same curated `OPS_INTEL.V_FINDINGS` API through a Vite proxy to port `5001`, using the read-only credentials in `api/.env`. Its staging inventory and ADF panels continue to use the backend at port `5000`, with `OPS_STAGE` as the staging schema. Start the findings API with:

```powershell
& '.\synthetic-data\.venv\Scripts\python.exe' -m flask --app api.app run --host 127.0.0.1 --port 5001
```

Then run `npm run dev` from `exasol-dashboard/` and open <http://127.0.0.1:5173/>. The intelligence route is read-only and uses the dedicated non-SYS API identity. The supplied backend's legacy SQL-generating RAG endpoint remains disabled; the maintained `api.app` assistant uses curated finding evidence only.

Data Requests use `GET /api/requests` and `POST /api/requests` on the port 5000 backend. They are persisted in a local SQLite file at `backend/instance/data_requests.sqlite3` (or the path set by `OPSNEXUS_REQUEST_DB`); they do not write to Exasol. The directory is ignored by Git. Azure Cost Management is exposed separately at `GET /api/azure/cost`; `GET /api/metrics/cost` reports Exasol cost metrics when `COST_USAGE_HISTORY` is available. This avoids the previous duplicate Flask route where both handlers claimed `/api/metrics/cost`.

Do not start the legacy port 5000 service until its local configuration uses an approved non-SYS identity and validated TLS. The dashboard integration work does not require restarting it; Logesh should perform that activation with his approved configuration.

The API has no authentication layer, so keep Flask bound to loopback for local use or place it behind an approved authenticated gateway before broader access. Do not expose the local development API publicly. The legacy backend refuses SYS, disabled certificate validation, unapproved schemas, and arbitrary SQL; its existing local `.env` must be updated with an approved non-SYS identity and validated TLS before its non-curated features can be used.
