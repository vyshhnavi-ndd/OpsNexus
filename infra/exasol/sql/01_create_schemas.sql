-- OpsNexus Exasol foundation. Proposed contract; review before production use.
-- Run with an administrative account. Do not put passwords in SQL files.
CREATE SCHEMA OPS_SOURCE;
CREATE SCHEMA OPS_STAGE;
CREATE SCHEMA OPS_INTEL;

-- OPS_SOURCE is reserved for optional source/reference data.
-- OPS_STAGE contains observed operational inputs from Module 1 and ADF.
-- OPS_INTEL contains analytical views/models and inferred intelligence outputs.
