async function jsonFetch(url, options) {
  const resp = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.error || `Request failed: ${resp.status}`);
  }
  return data;
}

function byId(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  byId(id).textContent = value;
}

function fmtBool(v) {
  if (v === true) return "true";
  if (v === false) return "false";
  return "-";
}

function fmtDate(s) {
  if (!s) return "-";
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

async function refreshRevisionsAndReplicas() {
  const revisionsBody = byId("revisionsBody");
  revisionsBody.innerHTML = `<tr><td colspan="3" class="muted">Loading...</td></tr>`;

  try {
    const rev = await jsonFetch("/api/revisions");
    const items = Array.isArray(rev.items) ? rev.items : [];

    if (items.length === 0) {
      revisionsBody.innerHTML = `<tr><td colspan="3" class="muted">No revisions found.</td></tr>`;
    } else {
      revisionsBody.innerHTML = items
        .slice(0, 50)
        .map((r) => {
          const name = r.name || "-";
          const active = r.properties?.active;
          const created = r.properties?.createdTime;
          return `<tr><td>${name}</td><td>${fmtBool(active)}</td><td>${fmtDate(created)}</td></tr>`;
        })
        .join("");
    }

    const rep = await jsonFetch("/api/replicas");
    setText("replicaCount", rep.count ?? "-");

    const replicaList = byId("replicaList");
    replicaList.innerHTML = "";
    const repItems = Array.isArray(rep.items) ? rep.items : [];
    repItems.slice(0, 50).forEach((x) => {
      const li = document.createElement("li");
      li.textContent = x.name || JSON.stringify(x);
      replicaList.appendChild(li);
    });
  } catch (e) {
    revisionsBody.innerHTML = `<tr><td colspan="3" class="warn">${e.message}</td></tr>`;
    setText("replicaCount", "-");
    byId("replicaList").innerHTML = "";
  }
}

async function startLoad() {
  const targetUrl = byId("targetUrl").value;
  const concurrency = Number(byId("concurrency").value);
  const durationSeconds = Number(byId("durationSeconds").value);
  const delayMs = Number(byId("delayMs").value);

  const st = byId("loadStatus");
  st.textContent = "Starting...";

  try {
    await jsonFetch("/api/load/start", {
      method: "POST",
      body: JSON.stringify({ targetUrl, concurrency, durationSeconds, delayMs }),
    });
  } catch (e) {
    st.textContent = e.message;
  }
}

async function stopLoad() {
  try {
    await jsonFetch("/api/load/stop", { method: "POST", body: "{}" });
  } catch {
    // ignore
  }
}

async function pollStatus() {
  try {
    const s = await jsonFetch("/api/load/status");
    setText("st_running", fmtBool(s.running));
    setText("st_sent", s.sent ?? "-");
    setText("st_succeeded", s.succeeded ?? "-");
    setText("st_failed", s.failed ?? "-");
    setText("st_lastError", s.lastError ?? "-");

    const st = byId("loadStatus");
    if (s.running) {
      st.textContent = `Running (${s.concurrency} workers, ${s.durationSeconds}s, delayMs=${s.delayMs})`;
    } else {
      st.textContent = "Idle";
    }
  } catch {
    // ignore
  }
}

document.addEventListener("DOMContentLoaded", () => {
  byId("refreshBtn").addEventListener("click", refreshRevisionsAndReplicas);
  byId("startBtn").addEventListener("click", startLoad);
  byId("stopBtn").addEventListener("click", stopLoad);

  pollStatus();
  setInterval(pollStatus, 1000);
});
