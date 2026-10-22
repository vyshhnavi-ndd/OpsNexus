# OpsNexus

OpsNexus combines a read-only Flask API for the Exasol intelligence findings with a React dashboard served by the same Flask application.

## Run the integrated application

Start Exasol Personal if it is not already running. From the repository root, start Flask:

```powershell
& '.\synthetic-data\.venv\Scripts\python.exe' -m flask --app api.app run --host 127.0.0.1 --port 5000
```

Open <http://127.0.0.1:5000/>. The Flask app serves the prebuilt dashboard and the `/health` and `/api/findings` endpoints on one origin. The dashboard uses only the configured read-only `OPSNEXUS_API` connection in `api/.env`; it does not need a separate frontend server in production mode.

Build the dashboard after changing `frontend/`:

```powershell
cd frontend
npm install
npm run build
cd ..
```

For frontend development with hot reload, run `npm run dev` from `frontend/` in another terminal; Vite proxies `/api` and `/health` to Flask on port 5000. See [dashboard setup](./docs/DASHBOARD_SETUP.md) for details and integration boundaries.

The original dashboard project Logesh supplied is retained under `git (2)/git/exasol-dashboard/` for reference. It is not used by the integrated build. ADF run history, cost/trust analytics, chat, and schema browsing require additional backend routes and are not presented as live features by this integrated dashboard.
