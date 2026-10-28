import React, { useCallback, useEffect, useState } from "react";
import Card from "../components/Card";
import SectionTitle from "../components/SectionTitle";
import Badge from "../components/Badge";

const API_URL = "http://127.0.0.1:5000/api";

export default function RequestsPage({ search = "" }) {
  const [schemas, setSchemas] = useState([]);
  const [tables, setTables] = useState([]);
  const [requests, setRequests] = useState([]);

  const [schema, setSchema] = useState("");
  const [table, setTable] = useState("");
  const [priority, setPriority] = useState("Medium");
  const [description, setDescription] = useState("");

  const [loadingSchemas, setLoadingSchemas] = useState(true);
  const [loadingTables, setLoadingTables] = useState(false);
  const [loadingRequests, setLoadingRequests] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const getErrorMessage = (data, fallback) =>
    data?.error?.message ||
    (typeof data?.error === "string" ? data.error : "") ||
    data?.message ||
    fallback;

  const fetchJson = async (url, options = {}) => {
    const response = await fetch(url, options);
    const contentType = response.headers.get("content-type") || "";

    if (!contentType.toLowerCase().includes("application/json")) {
      const body = await response.text();
      throw new Error(
        `API returned non-JSON content (HTTP ${response.status}). ` +
          body.slice(0, 150)
      );
    }

    const data = await response.json();

    if (!response.ok || data?.success === false) {
      throw new Error(
        getErrorMessage(data, `Request failed with HTTP ${response.status}.`)
      );
    }

    return data;
  };

  useEffect(() => {
    const loadSchemas = async () => {
      try {
        setLoadingSchemas(true);
        const data = await fetchJson(`${API_URL}/schemas`);

        const schemaList = data.schemas || data.data || [];
        if (!Array.isArray(schemaList)) {
          throw new Error("The schemas API did not return an array.");
        }

        setSchemas(
          schemaList
            .map((item) =>
              typeof item === "string"
                ? item
                : item.schema_name || item.name || item.schema
            )
            .filter(Boolean)
        );
      } catch (err) {
        setError(err.message);
      } finally {
        setLoadingSchemas(false);
      }
    };

    loadSchemas();
  }, []);

  useEffect(() => {
    if (!schema) {
      setTables([]);
      setTable("");
      return;
    }

    const loadTables = async () => {
      try {
        setLoadingTables(true);
        setTable("");

        const data = await fetchJson(
          `${API_URL}/tables?schema=${encodeURIComponent(schema)}`
        );

        const tableList = data.tables || data.data || [];
        if (!Array.isArray(tableList)) {
          throw new Error("The tables API did not return an array.");
        }

        setTables(
          tableList
            .map((item) =>
              typeof item === "string"
                ? item
                : item.table_name || item.name || item.table
            )
            .filter(Boolean)
        );
      } catch (err) {
        setTables([]);
        setError(err.message);
      } finally {
        setLoadingTables(false);
      }
    };

    setError("");
    loadTables();
  }, [schema]);

  const loadRequests = useCallback(async () => {
    try {
      setLoadingRequests(true);
      const data = await fetchJson(`${API_URL}/data-requests`);

      if (!Array.isArray(data.requests)) {
        throw new Error("Invalid requests API response.");
      }

      setRequests(data.requests);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingRequests(false);
    }
  }, []);

  useEffect(() => {
    loadRequests();
  }, [loadRequests]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (!schema || !table) {
      setError("Please select a schema and table.");
      return;
    }

    const trimmedDescription = description.trim();
    if (trimmedDescription.length < 5) {
      setError("Please enter a business justification of at least 5 characters.");
      return;
    }

    try {
      setSubmitting(true);

      const data = await fetchJson(`${API_URL}/data-requests`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          schema_name: schema,
          table_name: table,
          priority,
          description: trimmedDescription,
        }),
      });

      setSuccess(
        `Request submitted successfully. ID: ${data.request?.id || "Created"}`
      );
      setSchema("");
      setTable("");
      setPriority("Medium");
      setDescription("");
      await loadRequests();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };
  const normalizedSearch = String(search || "").toLowerCase();

  const visibleRequests = requests.filter((item) =>
    [
      item.id,
      item.dataset,
      item.schema_name,
      item.schema,
      item.table_name,
      item.description,
      item.reason,
      item.status,
      item.priority,
      item.ai_recommendation,
      item.risk_level,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(normalizedSearch)
  );

  return (
    <div className="page-two">
      <Card>
        <SectionTitle
          title="Submit a data request"
          subtitle="Select a schema and table, then explain your business need"
        />

        <form className="request-form" onSubmit={handleSubmit}>
          <div className="request-fields-row">
            <div className="request-field">
              <label htmlFor="request-priority">Priority</label>
              <select
                id="request-priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
              >
                <option value="Low">Low</option>
                <option value="Medium">Medium</option>
                <option value="High">High</option>
                <option value="Urgent">Urgent</option>
              </select>
            </div>

            <div className="request-field">
              <label htmlFor="request-schema">Select Schema</label>
              <select
                id="request-schema"
                value={schema}
                onChange={(e) => setSchema(e.target.value)}
                required
                disabled={loadingSchemas}
              >
                <option value="">
                  {loadingSchemas ? "Loading schemas..." : "Choose a schema"}
                </option>
                {schemas.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>

            <div className="request-field">
              <label htmlFor="request-table">Select Table</label>
              <select
                id="request-table"
                value={table}
                onChange={(e) => setTable(e.target.value)}
                required
                disabled={!schema || loadingTables}
              >
                <option value="">
                  {!schema
                    ? "Select a schema first"
                    : loadingTables
                      ? "Loading tables..."
                      : "Choose a table"}
                </option>
                {tables.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="request-field request-description">
            <label htmlFor="request-description">Business Justification</label>
            <textarea
              id="request-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Explain why you need this dataset and how it will be used..."
              minLength={5}
              maxLength={2000}
              rows={5}
              required
            />
          </div>

          {error && (
            <p className="request-error" role="alert">
              {error}
            </p>
          )}
          {success && (
            <p className="request-success" role="status">
              {success}
            </p>
          )}

          <div className="request-submit">
            <button
              className="btn btn-primary"
              type="submit"
              disabled={submitting || loadingSchemas || loadingTables}
            >
              {submitting ? "Submitting..." : "Submit Request"}
            </button>
          </div>
        </form>
      </Card>

      <Card>
        <SectionTitle
          title="Recent requests"
          subtitle="Requests saved in Exasol with AI review results"
        />

        <div className="request-toolbar">
          <span>
            {loadingRequests
              ? "Loading requests..."
              : `${visibleRequests.length} request(s)`}
          </span>
          <button
            type="button"
            className="btn"
            onClick={loadRequests}
            disabled={loadingRequests}
          >
            Refresh
          </button>
        </div>

        {loadingRequests ? (
          <div className="empty">Loading saved requests...</div>
        ) : visibleRequests.length > 0 ? (
          <div
            className="table-scroll"
            style={{ width: "100%", overflowX: "auto", overflowY: "hidden" }}
          >
            <table
              style={{
                width: "100%",
                minWidth: "1050px",
                tableLayout: "fixed",
                borderCollapse: "collapse",
              }}
            >
              <thead>
                <tr>
                  <th style={{ width: "100px", padding: "12px" }}>Request ID</th>
                  <th style={{ width: "120px", padding: "12px" }}>Schema</th>
                  <th style={{ width: "160px", padding: "12px" }}>Table</th>
                  <th style={{ width: "90px", padding: "12px" }}>Priority</th>
                  <th style={{ width: "110px", padding: "12px" }}>Status</th>
                  <th style={{ width: "280px", padding: "12px" }}>AI Recommendation</th>
                  <th style={{ width: "90px", padding: "12px" }}>Risk</th>
                  <th style={{ width: "150px", padding: "12px" }}>Created</th>
                </tr>
              </thead>
              <tbody>
                {visibleRequests.map((item) => (
                  <tr key={item.id}>
                    <td style={{ padding: "12px", verticalAlign: "top", overflowWrap: "anywhere" }}>{item.id}</td>
                    <td style={{ padding: "12px", verticalAlign: "top", overflowWrap: "anywhere" }}>{item.schema_name || item.schema || "—"}</td>
                    <td style={{ padding: "12px", verticalAlign: "top", overflowWrap: "anywhere" }}>{item.table_name || item.dataset || "—"}</td>
                    <td style={{ padding: "12px", verticalAlign: "top" }}>{item.priority || "Medium"}</td>
                    <td style={{ padding: "12px", verticalAlign: "top" }}>
                      <Badge>{item.status || "Pending"}</Badge>
                    </td>
                    <td style={{ padding: "10px 12px", verticalAlign: "top" }}>
                      <div
                        style={{
                          width: "100%",
                          maxWidth: "260px",
                          boxSizing: "border-box",
                          display: "flex",
                          flexDirection: "column",
                          alignItems: "flex-start",
                          gap: "8px",
                        }}
                      >
                        <Badge>
                          {item.ai_recommendation || "UNDER REVIEW"}
                        </Badge>
                        {item.ai_reasoning && (
                          <div
                            className="ai-reasoning"
                            title={item.ai_reasoning}
                            style={{
                              width: "100%",
                              maxHeight: "110px",
                              overflowY: "auto",
                              overflowX: "hidden",
                              boxSizing: "border-box",
                              padding: "9px 10px",
                              lineHeight: 1.45,
                              fontSize: "12px",
                              whiteSpace: "pre-wrap",
                              overflowWrap: "anywhere",
                              border: "1px solid var(--border-color, #d1d5db)",
                              borderRadius: "6px",
                              background: "var(--surface-secondary, rgba(127,127,127,0.06))",
                        }}
                          >
                            {item.ai_reasoning}
                          </div>
                        )}
                      </div>
                    </td>
                    <td style={{ padding: "12px", verticalAlign: "top" }}>{item.risk_level || "MEDIUM"}</td>
                    <td style={{ padding: "12px", verticalAlign: "top", whiteSpace: "normal" }}>
                      {item.created_at
                        ? new Date(item.created_at).toLocaleString()
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty">
            {error ? "Requests could not be loaded." : "No saved requests found."}
          </div>
        )}
      </Card>
    </div>
  );
}
