import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  createDataRequest,
  dashboardApiContract,
  listDataRequests,
  queryDataAssistant,
} from "../src/dashboardApi.js";

test("data requests use the shared route, fields, and response contract", async () => {
  const calls = [];
  const http = {
    get: async (...args) => {
      calls.push(["get", ...args]);
      return { data: { requests: [] } };
    },
    post: async (...args) => {
      calls.push(["post", ...args]);
      return { data: { success: true, request: { id: "REQ-1" } } };
    },
  };
  await listDataRequests(http);
  await createDataRequest(http, {
    dataset: "OPS_STAGE.STG_DATASETS",
    reason: "Review data",
    priority: "High",
    requester: "must not be sent",
  });
  assert.deepEqual(calls[0], ["get", "/api/requests", {}]);
  assert.deepEqual(calls[1], ["post", "/api/requests", {
    dataset: "OPS_STAGE.STG_DATASETS",
    reason: "Review data",
    priority: "High",
  }, {}]);
  assert.equal(dashboardApiContract.requests.listResponseKey, "requests");
  assert.equal(dashboardApiContract.requests.createResponseKey, "request");
});

test("assistant uses the findings RAG route and long local inference timeout", async () => {
  let call;
  const http = { post: async (...args) => {
    call = args;
    return { data: { answer: "ok", source_finding_ids: [] } };
  } };
  await queryDataAssistant(http, "Summarize findings");
  assert.equal(call[0], "/api/rag/query");
  assert.deepEqual(call[1], { question: "Summarize findings" });
  assert.equal(call[2].timeout, 210000);
  assert.equal(dashboardApiContract.assistant.upstream, "http://127.0.0.1:5001");
});

test("both dashboard entry points use the shared helpers and no legacy endpoints", async () => {
  const activeUi = await readFile(new URL("../src/App.jsx", import.meta.url), "utf8");
  const secondaryUi = await readFile(new URL("../src/pages/App.jsx", import.meta.url), "utf8");
  const viteConfig = await readFile(new URL("../vite.config.js", import.meta.url), "utf8");
  for (const source of [activeUi, secondaryUi]) {
    assert.match(source, /createDataRequest\(axios/);
    assert.match(source, /listDataRequests\(axios/);
    assert.match(source, /queryDataAssistant\(axios/);
    assert.doesNotMatch(source, /\/api\/chat\/message/);
  }
  assert.match(viteConfig, /dashboardApiContract\.assistant\.path/);
  assert.match(viteConfig, /dashboardApiContract\.assistant\.upstream/);
});
