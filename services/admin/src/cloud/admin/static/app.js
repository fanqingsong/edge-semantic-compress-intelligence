const tokenKey = "adminToken";
const views = ["overview", "analyses", "knowledge"];
let nextBefore = null;

function token() {
  return sessionStorage.getItem(tokenKey) || "";
}

function showLogin(message) {
  document.querySelector("#login").hidden = false;
  document.querySelector("#app").hidden = true;
  document.querySelector("#sign-out").hidden = true;
  const error = document.querySelector("#login-error");
  error.hidden = !message;
  error.textContent = message || "";
}

function showApp() {
  document.querySelector("#login").hidden = true;
  document.querySelector("#app").hidden = false;
  document.querySelector("#sign-out").hidden = false;
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", "Bearer " + token());
  const response = await fetch(path, Object.assign({}, options, { headers }));
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch (_error) {
      body = { error: "invalid_response" };
    }
  }
  if (response.status === 401) {
    sessionStorage.removeItem(tokenKey);
    showLogin("The token was rejected.");
    throw new Error("unauthorized");
  }
  if (!response.ok) {
    const error = new Error((body && body.error) || "request_failed");
    error.status = response.status;
    throw error;
  }
  return body;
}

function metric(label, value) {
  const card = document.createElement("div");
  card.className = "metric";
  const name = document.createElement("span");
  name.textContent = label;
  const number = document.createElement("strong");
  number.textContent = value === null || value === undefined ? "unavailable" : String(value);
  card.append(name, number);
  return card;
}

function clear(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function showError(id, error) {
  const node = document.querySelector(id);
  node.hidden = !error;
  node.textContent = error ? error.message : "";
}

async function loadStatus() {
  showError("#status-error", null);
  try {
    const status = await api("/api/status");
    const grid = document.querySelector("#status-grid");
    clear(grid);
    const edge = status.edge || {};
    grid.append(
      metric("Edge", edge.reachable ? "reachable" : "unavailable"),
      metric("Outbox events", edge.reachable ? edge.pending_count : null),
      metric("Outbox bytes", edge.reachable ? edge.pending_bytes : null),
      metric("Processed events", status.processed_count),
      metric("Analyses", status.analysis_count),
      metric("Knowledge cases", status.case_count)
    );
    const job = status.latest_job;
    grid.append(metric("Latest import", job ? job.status + " · " + job.filename : "none"));
  } catch (error) {
    if (error.message !== "unauthorized") {
      showError("#status-error", error);
    }
  }
}

function appendAnalysisRow(item) {
  const row = document.createElement("tr");
  row.addEventListener("click", () => loadAnalysis(item.event_id));
  [item.created_at, item.event_id, item.root_cause, item.case_count].forEach((value) => {
    const cell = document.createElement("td");
    cell.textContent = value === null || value === undefined ? "" : String(value);
    row.append(cell);
  });
  document.querySelector("#analysis-rows").append(row);
}

async function loadAnalyses(before) {
  showError("#analysis-error", null);
  const suffix = before ? "&before=" + encodeURIComponent(before) : "";
  try {
    const page = await api("/api/analyses?limit=50" + suffix);
    if (!before) {
      clear(document.querySelector("#analysis-rows"));
    }
    page.items.forEach(appendAnalysisRow);
    nextBefore = page.next_before;
    document.querySelector("#older-analyses").hidden = !nextBefore;
  } catch (error) {
    if (error.message !== "unauthorized") {
      showError("#analysis-error", error);
    }
  }
}

function addList(parent, title, values) {
  const heading = document.createElement("h3");
  heading.textContent = title;
  parent.append(heading);
  if (!values.length) {
    const empty = document.createElement("p");
    empty.textContent = "None";
    parent.append(empty);
    return;
  }
  const list = document.createElement("ul");
  values.forEach((value) => {
    const item = document.createElement("li");
    item.textContent = value;
    list.append(item);
  });
  parent.append(list);
}

async function loadAnalysis(eventId) {
  showError("#analysis-error", null);
  try {
    const detail = await api("/api/analyses/" + encodeURIComponent(eventId));
    const article = document.querySelector("#analysis-detail");
    clear(article);
    article.hidden = false;
    const title = document.createElement("h3");
    title.textContent = detail.event_id;
    const cause = document.createElement("p");
    cause.textContent = detail.root_cause || "No root cause";
    const uncertainty = document.createElement("p");
    uncertainty.textContent = "Uncertainty: " + (detail.uncertainty || "none recorded");
    article.append(title, cause, uncertainty);
    addList(article, "Evidence", detail.evidence || []);
    addList(article, "Recommendations", detail.recommendations || []);
    const casesTitle = document.createElement("h3");
    casesTitle.textContent = "Retrieved cases";
    article.append(casesTitle);
    (detail.cases || []).forEach((item) => {
      const block = document.createElement("p");
      block.textContent = [
        item.case_id,
        item.target_ip || "no IP",
        item.source,
        item.summary,
        item.resolution
      ].join(" — ");
      article.append(block);
    });
    if (!(detail.cases || []).length) {
      const empty = document.createElement("p");
      empty.textContent = "No cases were retrieved.";
      article.append(empty);
    }
  } catch (error) {
    if (error.message !== "unauthorized") {
      showError("#analysis-error", error);
    }
  }
}

function appendCaseRow(item) {
  const row = document.createElement("tr");
  [item.case_id, item.target_ip, item.source, item.summary, item.resolution].forEach((value) => {
    const cell = document.createElement("td");
    cell.textContent = value === null || value === undefined ? "" : String(value);
    row.append(cell);
  });
  document.querySelector("#case-rows").append(row);
}

async function loadCases() {
  showError("#knowledge-error", null);
  const params = new URLSearchParams();
  const targetIp = document.querySelector("#filter-ip").value.trim();
  const source = document.querySelector("#filter-source").value.trim();
  if (targetIp) {
    params.set("target_ip", targetIp);
  }
  if (source) {
    params.set("source", source);
  }
  const suffix = params.toString() ? "?" + params.toString() : "";
  try {
    const page = await api("/api/cases" + suffix);
    const rows = document.querySelector("#case-rows");
    clear(rows);
    page.items.forEach(appendCaseRow);
    if (!page.items.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 5;
      cell.textContent = "No cases";
      row.append(cell);
      rows.append(row);
    }
  } catch (error) {
    if (error.message !== "unauthorized") {
      showError("#knowledge-error", error);
    }
  }
}

async function pollJob(jobId) {
  const status = document.querySelector("#job-status");
  for (let attempt = 0; attempt < 60; attempt += 1) {
    const job = await api("/api/knowledge/jobs/" + jobId);
    status.textContent = job.status + (job.error ? ": " + job.error : "");
    if (job.status === "succeeded") {
      status.textContent = "Imported " + job.upserted + " cases, removed " + job.removed_stale + " stale";
      await loadCases();
      await loadStatus();
      return;
    }
    if (job.status === "failed") {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

function activate(view) {
  views.forEach((name) => {
    document.querySelector("#" + name).hidden = name !== view;
  });
  document.querySelectorAll(".nav button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
  if (view === "overview") {
    loadStatus();
  }
  if (view === "analyses") {
    loadAnalyses(null);
  }
  if (view === "knowledge") {
    loadCases();
  }
}

document.querySelector("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  sessionStorage.setItem(tokenKey, document.querySelector("#token").value);
  showApp();
  try {
    await loadStatus();
    activate("overview");
  } catch (_error) {
    return;
  }
});

document.querySelector("#sign-out").addEventListener("click", () => {
  sessionStorage.removeItem(tokenKey);
  showLogin("");
});

document.querySelectorAll(".nav button").forEach((button) => {
  button.addEventListener("click", () => activate(button.dataset.view));
});

document.querySelector("#refresh-status").addEventListener("click", loadStatus);
document.querySelector("#refresh-analyses").addEventListener("click", () => loadAnalyses(null));
document.querySelector("#older-analyses").addEventListener("click", () => loadAnalyses(nextBefore));
document.querySelector("#case-filter").addEventListener("submit", (event) => {
  event.preventDefault();
  loadCases();
});

document.querySelector("#upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.querySelector("#upload-file");
  const button = event.currentTarget.querySelector("button");
  const data = new FormData();
  data.append("file", input.files[0]);
  button.disabled = true;
  showError("#knowledge-error", null);
  try {
    const job = await api("/api/knowledge/documents", { method: "POST", body: data });
    document.querySelector("#job-status").textContent = job.status;
    await pollJob(job.id);
    input.value = "";
  } catch (error) {
    if (error.message !== "unauthorized") {
      showError("#knowledge-error", error);
    }
  } finally {
    button.disabled = false;
  }
});

if (token()) {
  showApp();
  activate("overview");
} else {
  showLogin("");
}
