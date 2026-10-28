# OpsNexus dashboard API contract

`contracts/dashboard_api.json` is the source of truth for routes and request
field names. The React dashboard uses the shared client in
`exasol-dashboard/src/dashboardApi.js`; the Flask route and Vite proxy read the
same contract. Keep frontend and backend changes aligned with that file.

## Data Requests

- `GET /api/requests` returns `{ "success": true, "requests": [...] }`.
- `POST /api/requests` accepts the fields below. `dataset_id` and
  `business_justification` are not aliases.

```json
{
  "dataset": "OPS_STAGE.STG_DATASETS",
  "reason": "Explain the business need",
  "priority": "High"
}
```

A successful create returns HTTP 201 with
`{ "success": true, "request": { "id", "dataset", "reason", "priority", "status", "created_at" } }`.
Validation errors return HTTP 400; unavailable local SQLite storage returns
HTTP 503. Requests are local workflow records and do not write to Exasol.

## Data Assistant

The dashboard sends `POST /api/rag/query` through Vite, which proxies that
path to the findings API on `127.0.0.1:5001`. It sends
`{ "question": "..." }` and allows up to 210 seconds for local Ollama
generation. A successful response contains `answer`, `model`, and
`source_finding_ids`; the UI displays those source IDs beneath the answer.

Invalid or missing questions return HTTP 400. An unavailable Ollama service,
missing model, or unavailable findings database returns HTTP 503. The
assistant only uses the curated findings view; it does not query ADF, billing,
staging tables, or data-request records.

## Missing metrics

An unavailable value is `null`, displayed as **Unavailable**. A feature with
no supporting table or compatible metric is displayed as **Not configured**.
A recorded numeric zero remains `0`; it is never used as a substitute for
missing data. For Azure billing, no returned cost rows are represented as
`recorded_cost_inr: null` with zero recorded days when billing responds, and
both fields are `null` when the billing service is unavailable.

## Demo acceptance checks

1. `GET /api/requests` loads the recent-request list; a create returns the
   same request object shape the UI inserts into that list.
2. Assistant answers arrive from `/api/rag/query` through the Vite proxy and
   show the returned finding IDs.
3. Missing trust and cost values read **Unavailable** or **Not configured**;
   an actual recorded zero stays zero.
4. For a full ADF-to-Exasol detection demonstration, the ADF run ID must match
   the source run ID referenced by an Exasol finding. Do not infer this link
   from similar timestamps or pipeline names.
