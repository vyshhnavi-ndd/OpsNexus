import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  AlertCircle,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Columns3,
  Database,
  Download,
  LoaderCircle,
  Play,
  RefreshCw,
  Rows3,
  Search,
  Table2,
  Terminal,
  Wifi,
  WifiOff,
} from "lucide-react";

const DEFAULT_SCHEMA = "OPS_STAGE";
const DEFAULT_LIMIT = 100;

function getErrorMessage(error, fallback = "Something went wrong.") {
  const payload = error?.response?.data;
  const apiError = payload?.error;

  if (typeof apiError === "string") return apiError;
  if (apiError && typeof apiError === "object") {
    return apiError.message || apiError.code || fallback;
  }

  return payload?.message || error?.message || fallback;
}

function normalizeColumns(columns = [], sampleRow = null) {
  if (Array.isArray(columns) && columns.length) {
    return columns
      .map((column, index) => {
        if (typeof column === "string") {
          return {
            column_name: column,
            data_type: "",
            nullable: "",
            ordinal_position: index + 1,
          };
        }

        return {
          column_name:
            column.column_name ||
            column.name ||
            column.columnName ||
            "",
          data_type:
            column.data_type ||
            column.type ||
            column.column_type ||
            "",
          nullable:
            column.nullable ??
            column.is_nullable ??
            column.column_is_nullable ??
            "",
          ordinal_position:
            column.ordinal_position ??
            column.position ??
            column.column_ordinal_position ??
            index + 1,
        };
      })
      .filter((column) => column.column_name);
  }

  if (sampleRow && typeof sampleRow === "object") {
    return Object.keys(sampleRow).map((column_name, index) => ({
      column_name,
      data_type: "",
      nullable: "",
      ordinal_position: index + 1,
    }));
  }

  return [];
}

function formatCell(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function DataGrid({ rows = [], columns = [], loading = false }) {
  const names = columns
    .map((column) => typeof column === "string" ? column : column.column_name || column.name)
    .filter(Boolean);

  if (loading) {
    return (
      <div className="exa-state">
        <LoaderCircle className="exa-spin" size={24} />
        <span>Loading records from Exasol…</span>
      </div>
    );
  }

  if (!rows.length || !names.length) {
    return (
      <div className="exa-state">
        <Rows3 size={25} />
        <strong>No rows to display</strong>
        <span>Choose a table or run a query that returns records.</span>
      </div>
    );
  }

  return (
    <div className="exa-grid-wrap">
      <table className="exa-grid">
        <thead>
          <tr>
            <th className="exa-row-number">#</th>
            {names.map((name) => <th key={name}>{name}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`${rowIndex}-${names[0] || "row"}`}>
              <td className="exa-row-number">{rowIndex + 1}</td>
              {names.map((name) => {
                const value = row[name] ?? row[name.toLowerCase()] ?? row[name.toUpperCase()];
                const formatted = formatCell(value);

                return (
                  <td key={name} title={formatted === null ? "NULL" : formatted}>
                    {formatted === null
                      ? <span className="exa-null">NULL</span>
                      : formatted}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ExasolDatabase({
  api = "/api",
  schemaDefault = DEFAULT_SCHEMA,
}) {
  const apiBase = useMemo(() => String(api || "").replace(/\/+$/, ""), [api]);

  const [schemas, setSchemas] = useState([]);
  const [schema, setSchema] = useState(schemaDefault);
  const [selected, setSelected] = useState(null);
  const [rows, setRows] = useState([]);
  const [columns, setColumns] = useState([]);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(DEFAULT_LIMIT);
  const [total, setTotal] = useState(null);
  const [tableSearch, setTableSearch] = useState("");
  const [rowFilter, setRowFilter] = useState("");
  const [tab, setTab] = useState("data");
  const [sql, setSql] = useState("SELECT CURRENT_SCHEMA AS SCHEMA_NAME");
  const [loadingStructure, setLoadingStructure] = useState(false);
  const [loadingTable, setLoadingTable] = useState(false);
  const [error, setError] = useState("");
  const [connected, setConnected] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  const loadStructure = useCallback(async () => {
    setLoadingStructure(true);
    setError("");

    try {
      const response = await axios.get(`${apiBase}/database-structure`, {
        timeout: 15000,
      });
      const payload = response.data || {};

      if (payload.success === false) {
        throw new Error(getErrorMessage({ response }, "Unable to load database structure."));
      }

      const rawSchemas = payload.schemas || payload.structure || payload.data || [];
      let groups = Array.isArray(rawSchemas)
        ? rawSchemas.map((item) => {
            const schemaName =
              item.schema_name || item.name || item.schema || schemaDefault;

            return {
              schema_name: schemaName,
              tables: (item.tables || []).map((table) => ({
                ...table,
                table_schema:
                  table.table_schema || table.schema_name || schemaName,
                table_name: table.table_name || table.name,
                columns: normalizeColumns(table.columns || []),
              })).filter((table) => table.table_name),
            };
          })
        : [];

      // Fall back if schemas are missing OR none contains usable table metadata.
      // The structure endpoint can return a schema whose table objects have no table_name.
      const hasUsableTables = groups.some(
        (group) => Array.isArray(group.tables) && group.tables.length > 0
      );

      if (!groups.length || !hasUsableTables) {
        const responseTables = await axios.get(`${apiBase}/tables`, {
          params: { schema: schemaDefault },
          timeout: 15000,
        });
        const tablePayload = responseTables.data || {};

        if (tablePayload.success === false) {
          throw new Error(getErrorMessage({ response: responseTables }, "Unable to load tables."));
        }

        const rawTables = tablePayload.tables || tablePayload.data || [];
        const fallbackGroup = {
          schema_name: tablePayload.schema || schemaDefault,
          tables: rawTables.map((table) => ({
            ...table,
            table_schema: table.table_schema || tablePayload.schema || schemaDefault,
            table_name: table.table_name || table.name,
            columns: normalizeColumns(table.columns || []),
          })).filter((table) => table.table_name),
        };

        if (fallbackGroup.tables.length > 0) {
          const fallbackName = String(fallbackGroup.schema_name).toUpperCase();
          const existing = groups.filter(
            (group) =>
              group.tables.length > 0 &&
              String(group.schema_name).toUpperCase() !== fallbackName
          );
          groups = [...existing, fallbackGroup];
        }
      }

      setSchemas(groups);
      setSchema((current) =>
        groups.find(
          (item) =>
            String(item.schema_name).toUpperCase() === String(current).toUpperCase()
        )?.schema_name ||
        groups.find(
          (item) =>
            String(item.schema_name).toUpperCase() === String(schemaDefault).toUpperCase()
        )?.schema_name ||
        groups[0]?.schema_name ||
        schemaDefault
      );
      setConnected(true);
      setLastUpdated(new Date());
    } catch (requestError) {
      setConnected(false);
      setError(getErrorMessage(requestError, "Cannot reach Flask API. Check that Flask is running and the API URL is correct."));
    } finally {
      setLoadingStructure(false);
    }
  }, [apiBase, schemaDefault]);

  useEffect(() => {
    const timer = window.setTimeout(loadStructure, 0);
    return () => window.clearTimeout(timer);
  }, [loadStructure]);

  const activeSchema = schemas.find((item) => item.schema_name === schema);

  const visibleTables = useMemo(() => {
    const search = tableSearch.trim().toLowerCase();
    return (activeSchema?.tables || []).filter((table) =>
      String(table.table_name || "").toLowerCase().includes(search)
    );
  }, [activeSchema, tableSearch]);

  const openTable = useCallback(async (table, nextOffset = 0) => {
    const tableName = table?.table_name || table?.name;
    if (!tableName) return;

    const schemaName = table.table_schema || schema;
    setSelected({ table_schema: schemaName, table_name: tableName });
    setOffset(nextOffset);
    setRows([]);
    setColumns(normalizeColumns(table.columns || []));
    setTotal(null);
    setLoadingTable(true);
    setError("");
    setRowFilter("");
    setTab("data");

    try {
      const response = await axios.get(
        `${apiBase}/tables/${encodeURIComponent(schemaName)}/${encodeURIComponent(tableName)}`,
        {
          params: { limit, offset: nextOffset },
          timeout: 20000,
        }
      );
      const payload = response.data || {};

      if (payload.success === false) {
        throw new Error(getErrorMessage({ response }, "Unable to load table records."));
      }

      const data = Array.isArray(payload.data)
        ? payload.data
        : Array.isArray(payload.rows)
          ? payload.rows
          : [];

      setRows(data);
      setTotal(payload.total_rows ?? payload.total ?? payload.count ?? null);
      setColumns(normalizeColumns(payload.columns || table.columns || [], data[0] || null));
      setConnected(true);
      setLastUpdated(new Date());
    } catch (requestError) {
      setError(getErrorMessage(requestError, `Unable to load ${schemaName}.${tableName}.`));
    } finally {
      setLoadingTable(false);
    }
  }, [apiBase, schema, limit]);

  async function changePage(nextOffset) {
    if (!selected || nextOffset < 0) return;
    await openTable(selected, nextOffset);
  }

  const visibleRows = useMemo(() => {
    const search = rowFilter.trim().toLowerCase();
    if (!search) return rows;

    return rows.filter((row) =>
      Object.values(row).some((value) =>
        String(value ?? "NULL").toLowerCase().includes(search)
      )
    );
  }, [rows, rowFilter]);

  const dataColumns = normalizeColumns(columns, rows[0] || null);

  function exportCsv(data, columnList, fileName) {
    const names = columnList.map((column) =>
      typeof column === "string" ? column : column.column_name || column.name
    ).filter(Boolean);

    if (!data.length || !names.length) return;

    const quote = (value) =>
      `"${String(value ?? "").replace(/"/g, '""')}"`;
    const csv = [
      names.map(quote).join(","),
      ...data.map((row) =>
        names.map((name) => quote(row[name] ?? row[name.toLowerCase()] ?? row[name.toUpperCase()])).join(",")
      ),
    ].join("\r\n");

    const blob = new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = fileName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  const tableCount = (activeSchema?.tables || []).length;

  return (
    <main className="exa-page">
      <header className="exa-page-header">
        <div className="exa-brand">
          <div className="exa-brand-icon"><Database size={22} /></div>
          <div>
            <p className="exa-eyebrow">OPSNEXUS / DATA PLATFORM</p>
            <h1>Exasol Explorer</h1>
            <p className="exa-subtitle">Browse schemas, inspect records, and run read-only SQL queries.</p>
          </div>
        </div>
        <div className={`exa-status ${connected ? "is-connected" : "is-offline"}`}>
          {connected ? <Wifi size={15} /> : <WifiOff size={15} />}
          <span>{connected ? "API connected" : "API unavailable"}</span>
        </div>
      </header>

      <section className="exa-summary">
        <article className="exa-summary-card">
          <span className="exa-summary-icon"><Database size={17} /></span>
          <div><span className="exa-summary-label">Database</span><strong>Exasol</strong></div>
        </article>
        <article className="exa-summary-card">
          <span className="exa-summary-icon"><LayersIcon /></span>
          <div><span className="exa-summary-label">Active schema</span><strong>{schema || "—"}</strong></div>
        </article>
        <article className="exa-summary-card">
          <span className="exa-summary-icon"><Table2 size={17} /></span>
          <div><span className="exa-summary-label">Tables in schema</span><strong>{tableCount}</strong></div>
        </article>
        <article className="exa-summary-card">
          <span className="exa-summary-icon"><Rows3 size={17} /></span>
          <div><span className="exa-summary-label">Rows loaded</span><strong>{rows.length}</strong></div>
        </article>
      </section>

      {error && (
        <div className="exa-alert" role="alert">
          <AlertCircle size={18} />
          <div><strong>Request failed</strong><span>{error}</span></div>
          <button className="exa-alert-action" onClick={loadStructure}>Retry</button>
        </div>
      )}

      <div className="exa-workspace">
        <aside className="exa-sidebar">
          <div className="exa-sidebar-heading">
            <div><h2>Database objects</h2><p>Browse available tables</p></div>
            <button className="exa-icon-button" onClick={loadStructure} disabled={loadingStructure} title="Refresh schemas">
              <RefreshCw size={16} className={loadingStructure ? "exa-spin" : ""} />
            </button>
          </div>

          <label className="exa-field-label" htmlFor="exa-schema">Schema</label>
          <select
            id="exa-schema"
            className="exa-select"
            value={schema}
            onChange={(event) => {
              setSchema(event.target.value);
              setSelected(null);
              setRows([]);
              setColumns([]);
              setTotal(null);
              setOffset(0);
              setTab("data");
            }}
          >
            {schemas.length
              ? schemas.map((item) => <option key={item.schema_name} value={item.schema_name}>{item.schema_name}</option>)
              : <option value={schemaDefault}>{schemaDefault}</option>}
          </select>

          <div className="exa-search">
            <Search size={16} />
            <input
              id="exa-table-search"
              name="tableSearch"
              value={tableSearch}
              onChange={(event) => setTableSearch(event.target.value)}
              placeholder="Search tables…"
              aria-label="Search tables"
            />
            {tableSearch && <button onClick={() => setTableSearch("")} aria-label="Clear table search">×</button>}
          </div>

          <div className="exa-object-count">
            <span>TABLES</span><span>{visibleTables.length}</span>
          </div>

          <div className="exa-table-list">
            {loadingStructure && !schemas.length ? (
              <div className="exa-sidebar-loading"><LoaderCircle size={18} className="exa-spin" /> Loading schema…</div>
            ) : visibleTables.length ? (
              visibleTables.map((table) => {
                const name = table.table_name || table.name;
                const isActive = selected?.table_name === name && selected?.table_schema === (table.table_schema || schema);
                return (
                  <button
                    key={`${table.table_schema || schema}.${name}`}
                    className={`exa-object-button ${isActive ? "is-active" : ""}`}
                    onClick={() => openTable(table, 0)}
                  >
                    <Table2 size={16} />
                    <span title={name}>{name}</span>
                    <ChevronRight size={14} className="exa-object-chevron" />
                  </button>
                );
              })
            ) : (
              <div className="exa-empty-sidebar">
                <Database size={22} />
                  <strong>No approved tables are visible</strong>
                  <span>This identity may lack OPS_STAGE metadata access; this does not prove the tables are absent.</span>
              </div>
            )}
          </div>

          <div className="exa-sidebar-footer">
            <span className={`exa-small-dot ${connected ? "online" : ""}`} />
            <span>{connected ? "Flask connection available" : "Waiting for Flask API"}</span>
          </div>
        </aside>

        <section className="exa-content">
          <div className="exa-content-toolbar">
            <div>
              <p className="exa-eyebrow">WORKSPACE</p>
              <h2>{selected ? `${selected.table_schema}.${selected.table_name}` : "Query workspace"}</h2>
              <p>{selected ? "Preview and filter table records." : "Select a table or execute a read-only SQL query."}</p>
            </div>
            <div className="exa-toolbar-actions">
              <label className="exa-limit-control">
                <span>Rows</span>
                <select
                  id="exa-row-limit"
                  name="rowLimit"
                  value={limit}
                  onChange={(event) => {
                    const nextLimit = Number(event.target.value);
                    setLimit(nextLimit);
                    if (selected) {
                      setOffset(0);
                      setRows([]);
                    }
                  }}
                >
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                  <option value={250}>250</option>
                </select>
              </label>
              <button className="exa-button" onClick={() => selected && openTable(selected, offset)} disabled={!selected || loadingTable}>
                <RefreshCw size={15} /> Reload
              </button>
              <button className="exa-button exa-button-primary" onClick={() => exportCsv(visibleRows, dataColumns, `${selected?.table_name || "exasol"}-rows.csv`)} disabled={!rows.length}>
                <Download size={15} /> Export CSV
              </button>
            </div>
          </div>

          <nav className="exa-tabs" aria-label="Database workspace tabs">
            <button className={tab === "data" ? "is-active" : ""} onClick={() => setTab("data")}><Rows3 size={15} /> Table data</button>
            <button className={tab === "columns" ? "is-active" : ""} onClick={() => setTab("columns")}><Columns3 size={15} /> Columns</button>
            <button className={tab === "sql" ? "is-active" : ""} onClick={() => setTab("sql")}><Terminal size={15} /> SQL editor (disabled)</button>
          </nav>

          {tab === "sql" ? (
            <section className="exa-sql-panel">
              <div className="exa-sql-panel-header">
                <div><Terminal size={17} /><strong>SQL console</strong></div>
                <span className="exa-readonly-badge"><CheckCircle2 size={13} /> Read-only</span>
              </div>
              <p className="exa-sql-help">SQL execution is disabled by the Flask backend. Browse approved tables below.</p>
              <textarea
                id="exa-sql-query"
                name="sqlQuery"
                className="exa-sql-editor"
                value={sql}
                disabled
                onChange={(event) => setSql(event.target.value)}
                spellCheck="false"
                aria-label="SQL query editor"
                placeholder="SELECT CURRENT_SCHEMA AS SCHEMA_NAME"
              />
              <div className="exa-sql-actions">
                <span>Exasol SQL</span>
                <button className="exa-button exa-button-primary" disabled>
                  <Play size={15} /> SQL execution disabled
                </button>
              </div>
            </section>
          ) : tab === "columns" ? (
            <section className="exa-table-panel">
              <div className="exa-panel-heading"><div><h3>Column details</h3><p>Names and metadata returned by Exasol.</p></div><span>{dataColumns.length} columns</span></div>
              {!selected ? (
                <div className="exa-state"><Columns3 size={24} /><strong>Select a table first</strong><span>Choose a table from the database objects panel.</span></div>
              ) : dataColumns.length ? (
                <div className="exa-grid-wrap">
                  <table className="exa-grid">
                    <thead><tr><th>#</th><th>Column name</th><th>Data type</th><th>Nullable</th></tr></thead>
                    <tbody>{dataColumns.map((column, index) => {
                      const name = column.column_name;
                      const found = columns.find((item) => (item.column_name || item.name) === name) || column;
                      return <tr key={name}><td>{found.ordinal_position || found.position || index + 1}</td><td><strong>{name}</strong></td><td>{found.data_type || found.type || "—"}</td><td>{String(found.nullable ?? found.is_nullable ?? "—")}</td></tr>;
                    })}</tbody>
                  </table>
                </div>
              ) : (
                <div className="exa-state"><Columns3 size={24} /><strong>No column metadata</strong><span>Open a table to load its columns.</span></div>
              )}
            </section>
          ) : (
            <section className="exa-table-panel">
              <div className="exa-panel-heading">
                <div><h3>Table records</h3><p>{selected ? `Viewing ${selected.table_name}` : "Your selected table records will appear here."}</p></div>
                {selected && <span className="exa-total-badge">{total == null ? `${rows.length} loaded` : `${Number(total).toLocaleString()} total rows`}</span>}
              </div>
              {selected && (
                <div className="exa-data-controls">
                  <div className="exa-search exa-row-search">
                    <Search size={16} />
                    <input id="exa-row-filter" name="rowFilter" value={rowFilter} onChange={(event) => setRowFilter(event.target.value)} placeholder="Filter loaded records…" aria-label="Filter loaded records" />
                    {rowFilter && <button onClick={() => setRowFilter("")} aria-label="Clear row filter">×</button>}
                  </div>
                  <span>{visibleRows.length} shown</span>
                </div>
              )}
              {!selected ? (
                <div className="exa-welcome">
                  <div className="exa-welcome-icon"><Database size={30} /></div>
                  <h3>Explore your Exasol data</h3>
                  <p>Select a schema and table on the left, or open the SQL editor to query your database.</p>
                  <button className="exa-button exa-button-primary" onClick={() => setTab("sql")}><Terminal size={15} /> Open SQL editor</button>
                </div>
              ) : (
                <>
                  <DataGrid rows={visibleRows} columns={dataColumns} loading={loadingTable} />
                  <footer className="exa-pagination">
                    <span>{rows.length ? `${offset + 1}–${offset + rows.length}` : "0 records"}{total != null ? ` of ${Number(total).toLocaleString()}` : ""}</span>
                    <div>
                      <button className="exa-button" onClick={() => changePage(offset - limit)} disabled={loadingTable || offset <= 0}><ChevronLeft size={15} /> Previous</button>
                      <button className="exa-button" onClick={() => changePage(offset + limit)} disabled={loadingTable || rows.length < limit || (total != null && offset + limit >= Number(total))}>Next <ChevronRight size={15} /></button>
                    </div>
                  </footer>
                </>
              )}
            </section>
          )}

          <div className="exa-page-footnote">
            <span>{lastUpdated ? `Last updated ${lastUpdated.toLocaleTimeString()}` : "Waiting for first successful API response"}</span>
            <span>OpsNexus · Exasol Data Explorer</span>
          </div>
        </section>
      </div>
    </main>
  );
}

function LayersIcon() {
  return <Columns3 size={17} />;
}
