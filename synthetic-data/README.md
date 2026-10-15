# OpsNexus Module 1 — Synthetic Data & Scenario Generation

This Python package generates deterministic synthetic operational records for the Module 2 ADF handoff. Runtime dependencies are standard-library only. Setuptools is used only to build/install the package. It creates no Azure resources, makes no Azure calls, and uses no cloud credentials. Every generated record is synthetic; it is not evidence from a live system.

## Runtime and setup

Python 3.11 or later is required. The implementation and installation workflow were exercised with Python 3.14.6. From this directory in PowerShell:

```powershell
& 'C:\Users\vyshh\AppData\Local\Python\bin\python.exe' -m venv .venv
& '.venv\Scripts\python.exe' -m pip install -e .
```

Use the team's approved Python executable if that path is not present in another environment. The `.venv` is project-local and ignored by Git.

## Generate and validate

```powershell
& '.venv\Scripts\python.exe' -m opsnexus_synthetic generate --seed 20261014 --out examples/seed-20261014
& '.venv\Scripts\python.exe' -m opsnexus_synthetic validate examples/seed-20261014
```

Generation writes CSV files under `examples/seed-20261014/data/`, `manifest.json`, `validation-report.json`, and the non-operational truth file under `ground_truth/`. A validation error produces a nonzero process exit code and a report with actionable error codes.

## Tests

```powershell
& '.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_*.py' -v
```

## Contract status and limitations

Schema version `2.0.0`, file names, row keys, and scenario fixtures are implemented by Module 1. They are **proposed inter-module contracts** until Person A/Person B confirm them. Consult [the handoff](../docs/MODULE_1_TO_MODULE_2_HANDOFF.md) before building ingestion. Semantic scenario labels and expected outcomes are kept in the separate ground-truth JSON; operational files use opaque scenario-instance IDs. The package emits no recovery actions or verification results.
