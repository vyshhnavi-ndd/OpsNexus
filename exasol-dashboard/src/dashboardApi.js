import contract from "../../contracts/dashboard_api.json" with { type: "json" };

export { contract as dashboardApiContract };

export function listDataRequests(http, options = {}) {
  return http.get(contract.requests.path, options);
}

export function createDataRequest(http, request, options = {}) {
  const payload = Object.fromEntries(
    contract.requests.createRequestFields.map((field) => [field, request[field]])
  );
  return http.post(contract.requests.path, payload, options);
}

export function queryDataAssistant(http, question, options = {}) {
  return http.post(
    contract.assistant.path,
    { [contract.assistant.questionField]: question },
    { timeout: contract.assistant.timeoutMs, ...options }
  );
}
