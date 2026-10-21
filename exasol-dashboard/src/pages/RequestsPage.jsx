import Card from "../components/Card";
import SectionTitle from "../components/SectionTitle";
import Badge from "../components/Badge";

export default function RequestsPage({
  requests,
  form,
  setForm,
  onSubmit,
  search = "",
  loading = false,
  error = "",
  onRefresh,
}) {
  const query = search.trim().toLowerCase();
  const visible = requests.filter((request) =>
    `${request.id} ${request.dataset} ${request.reason} ${request.status}`
      .toLowerCase()
      .includes(query)
  );
  const update = (key, value) => setForm((old) => ({ ...old, [key]: value }));

  return (
    <div className="page-two">
      <Card>
        <SectionTitle
          title="Submit a data request"
          subtitle="Describe the dataset and why it is needed"
        />
        <p className="request-storage-note">
          Requests are stored locally by the backend and are separate from Exasol data.
        </p>
        {error && <div className="notice" role="alert">{error}</div>}
        <form className="form-grid" onSubmit={onSubmit}>
          <label className="field">
            Dataset or table
            <input
              value={form.dataset}
              onChange={(event) => update("dataset", event.target.value)}
              placeholder="e.g. CUSTOMER_SALES"
              maxLength={200}
              required
            />
          </label>
          <label className="field">
            Priority
            <select value={form.priority} onChange={(event) => update("priority", event.target.value)}>
              <option>Low</option><option>Medium</option><option>High</option><option>Urgent</option>
            </select>
          </label>
          <label className="field span-two">
            Business justification
            <textarea
              value={form.reason}
              onChange={(event) => update("reason", event.target.value)}
              placeholder="Explain the business need…"
              maxLength={4000}
              required
            />
          </label>
          <div className="span-two">
            <button className="btn btn-primary" type="submit" disabled={loading}>
              {loading ? "Saving…" : "Submit request"}
            </button>
          </div>
        </form>
      </Card>

      <Card>
        <SectionTitle
          title="Recent requests"
          subtitle="Requests saved by this local backend"
          action={<button className="btn" type="button" onClick={onRefresh} disabled={loading}>Refresh</button>}
        />
        {loading && !requests.length ? <div className="empty">Loading requests…</div> :
          visible.length ? (
            <div className="table-scroll">
              <table>
                <thead><tr><th>Request ID</th><th>Dataset</th><th>Priority</th><th>Status</th></tr></thead>
                <tbody>{visible.map((item) => (
                  <tr key={item.id}>
                    <td>{item.id}</td><td>{item.dataset}</td><td>{item.priority}</td><td><Badge>{item.status}</Badge></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          ) : <div className="empty">{error ? "Request service is unavailable." : "No requests yet."}</div>
        }
      </Card>
    </div>
  );
}
