import os
import math
from datetime import datetime, timedelta
from fnmatch import fnmatch
from typing import Optional, List, Dict, Any

import requests
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

# -----------------------
# Configuration
# -----------------------

AZDO_ORG = os.getenv("AZDO_ORG")          # e.g. "myorg"
AZDO_PROJECT = os.getenv("AZDO_PROJECT")  # e.g. "MyProject"
AZDO_PAT = os.getenv("AZDO_PAT")          # Personal Access Token with Build (Read) access

if not AZDO_ORG or not AZDO_PROJECT or not AZDO_PAT:
    print("WARNING: AZDO_ORG, AZDO_PROJECT, and AZDO_PAT env vars must be set before this will work.")

AZDO_BASE_URL = f"https://dev.azure.com/{AZDO_ORG}" if AZDO_ORG else ""

# -----------------------
# FastAPI app setup
# -----------------------

app = FastAPI(title="Azure DevOps Pipeline Runtime Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # relax for local / dashboard embedding
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------
# Helpers
# -----------------------

def parse_azdo_time(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    # Azure DevOps timestamps end with 'Z' for UTC, e.g. "2025-11-12T08:32:02.34Z"
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def azdo_auth_header() -> Dict[str, str]:
    # Basic auth with PAT: user can be blank, PAT as password
    # This is equivalent to requests.auth.HTTPBasicAuth('', AZDO_PAT), but we build header ourselves.
    import base64
    token = f":{AZDO_PAT}".encode("utf-8")
    b64 = base64.b64encode(token).decode("utf-8")
    return {"Authorization": f"Basic {b64}"}


def normalize_branch(branch: str) -> str:
    branch = branch.strip()
    if not branch:
        return branch
    if branch.startswith("refs/"):
        return branch
    return f"refs/heads/{branch}"


def branch_has_wildcard(branch: str) -> bool:
    return any(symbol in branch for symbol in ("*", "?", "[", "]"))


def fetch_builds(
    branch: Optional[str],
    days: int,
    top: int,
) -> Dict[str, Any]:
    if not AZDO_BASE_URL:
        raise HTTPException(status_code=500, detail="Server not configured with Azure DevOps org URL.")

    url = f"{AZDO_BASE_URL}/{AZDO_PROJECT}/_apis/build/builds"
    min_time = datetime.utcnow() - timedelta(days=days)

    params = {
        "api-version": "7.1-preview.7",
        # queueTimeDescending cannot be combined with statusFilter=completed; use
        # finishTimeDescending so we still get the most recent completed builds.
        "statusFilter": "completed",
        "queryOrder": "finishTimeDescending",
        "top": top,
        "minTime": min_time.isoformat() + "Z",
    }

    if branch:
        params["branchName"] = branch

    headers = {
        "Content-Type": "application/json",
        **azdo_auth_header(),
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
    except requests.exceptions.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach Azure DevOps: {exc}") from exc
    if resp.status_code != 200:
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Azure DevOps API returned {resp.status_code}: {resp.text}",
        )

    return resp.json()


def strip_refs_heads(branch: Optional[str]) -> Optional[str]:
    if branch and branch.startswith("refs/heads/"):
        return branch[len("refs/heads/"):]
    return branch


def transform_builds(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    builds_out: List[Dict[str, Any]] = []
    for b in raw.get("value", []):
        start = parse_azdo_time(b.get("startTime"))
        finish = parse_azdo_time(b.get("finishTime"))

        duration_seconds = None
        duration_minutes = None
        if start and finish:
            delta = finish - start
            duration_seconds = delta.total_seconds()
            duration_minutes = round(duration_seconds / 60.0, 2)

        # Try to get a web URL
        web_url = b.get("webUrl")
        if not web_url:
            # Fallback: build URL manually
            build_id = b.get("id")
            if AZDO_ORG and AZDO_PROJECT and build_id:
                web_url = f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/_build/results?buildId={build_id}"

        builds_out.append(
            {
                "id": b.get("id"),
                "buildNumber": b.get("buildNumber"),
                "pipelineName": (b.get("definition") or {}).get("name"),
                "sourceBranch": b.get("sourceBranch"),
                "sourceBranchDisplay": strip_refs_heads(b.get("sourceBranch")),
                "result": b.get("result"),
                "status": b.get("status"),
                "startTime": b.get("startTime"),
                "finishTime": b.get("finishTime"),
                "durationSeconds": duration_seconds,
                "durationMinutes": duration_minutes,
                "webUrl": web_url,
            }
        )

    return builds_out


# -----------------------
# API Routes
# -----------------------

@app.get("/", response_class=HTMLResponse)
def index():
    # Simple HTML/JS frontend
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Azure DevOps Pipeline Runtime Dashboard</title>
  <style>
    :root {
      --bg: #f5f5f5;
      --card-bg: #fff;
      --text: #1f2937;
      --muted-text: #4b5563;
      --table-border: #e5e7eb;
      --table-header: #f9fafb;
      --row-hover: #f3f4f6;
      --input-bg: #fff;
      --input-border: #d1d5db;
      --button-bg: #2563eb;
      --button-text: #fff;
      --error-bg: #fee2e2;
      --error-text: #991b1b;
    }
    body.dark {
      --bg: #0f172a;
      --card-bg: #1f2937;
      --text: #f3f4f6;
      --muted-text: #cbd5f5;
      --table-border: #374151;
      --table-header: #1e293b;
      --row-hover: #273449;
      --input-bg: #0f172a;
      --input-border: #334155;
      --button-bg: #38bdf8;
      --button-text: #0f172a;
      --error-bg: #991b1b;
      --error-text: #fee2e2;
    }
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      padding: 1rem 2rem 3rem 2rem;
      background: var(--bg);
      color: var(--text);
      transition: background 0.3s ease, color 0.3s ease;
    }
    h1 {
      margin-top: 0;
    }
    .card {
      background: var(--card-bg);
      border-radius: 12px;
      padding: 1rem 1.5rem;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15);
      margin-bottom: 1rem;
    }
    .filters {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      align-items: flex-end;
    }
    .field {
      display: flex;
      flex-direction: column;
      font-size: 0.9rem;
    }
    .field label {
      margin-bottom: 0.25rem;
    }
    .field input, .field select {
      padding: 0.4rem 0.6rem;
      border-radius: 6px;
      border: 1px solid var(--input-border);
      background: var(--input-bg);
      color: var(--text);
      min-width: 160px;
    }
    button {
      padding: 0.5rem 0.9rem;
      border-radius: 6px;
      border: none;
      cursor: pointer;
      background: var(--button-bg);
      color: var(--button-text);
      font-weight: 600;
      transition: background 0.2s ease;
    }
    button:disabled {
      opacity: 0.6;
      cursor: default;
    }
    table {
      border-collapse: collapse;
      width: 100%;
      font-size: 0.85rem;
      table-layout: fixed;
    }
    th, td {
      padding: 0.4rem 0.5rem;
      border-bottom: 1px solid var(--table-border);
      text-align: left;
      color: var(--text);
    }
    th {
      background: var(--table-header);
      position: relative;
    }
    th .resizer {
      position: absolute;
      top: 0;
      right: 0;
      width: 8px;
      height: 100%;
      cursor: col-resize;
      user-select: none;
      display: inline-block;
    }
    th .resizer::after {
      content: "";
      position: absolute;
      top: 0;
      bottom: 0;
      left: 50%;
      width: 1px;
      background: var(--table-border);
      transform: translateX(-50%);
    }
    body.resizing,
    body.resizing * {
      cursor: col-resize !important;
      user-select: none !important;
    }
    tr:hover {
      background: var(--row-hover);
    }
    .badge {
      display: inline-block;
      padding: 0.1rem 0.4rem;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 600;
    }
    .badge-success {
      background: #dcfce7;
      color: #166534;
    }
    .badge-failed {
      background: #fee2e2;
      color: #b91c1c;
    }
    .badge-other {
      background: #e0f2fe;
      color: #075985;
    }
    .summary {
      font-size: 0.85rem;
      color: var(--muted-text);
      margin-top: 0.5rem;
    }
    .summary span {
      margin-right: 1rem;
    }
    .nowrap {
      white-space: nowrap;
    }
    .error-banner {
      margin-top: 0.75rem;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      background: #fee2e2;
      color: #991b1b;
      display: none;
    }
  </style>
</head>
<body>
  <h1>Azure DevOps Pipeline Runtime Dashboard</h1>
  <div class="card">
    <div class="filters">
      <div class="field">
        <label for="branchInput">Branch (supports wildcards, e.g. <code>release/*</code>)</label>
        <input id="branchInput" type="text" placeholder="main, refs/heads/main, release/* (blank = all)" />
      </div>
      <div class="field">
        <label for="daysInput">Lookback (days)</label>
        <input id="daysInput" type="number" min="1" max="365" value="7" />
      </div>
      <div class="field">
        <label for="topInput">Max builds to fetch</label>
        <input id="topInput" type="number" min="1" max="1000" value="200" />
      </div>
      <div class="field">
        <label for="pipelineFilter">Filter by pipeline name (contains)</label>
        <input id="pipelineFilter" type="text" placeholder="e.g. api-service" />
      </div>
      <div class="field">
        <label for="statusFilter">Build status</label>
        <select id="statusFilter">
          <option value="all">All</option>
          <option value="succeeded">Succeeded</option>
          <option value="partiallysucceeded">Partially succeeded</option>
          <option value="failed">Failed</option>
          <option value="canceled">Canceled</option>
          <option value="other">Other</option>
        </select>
      </div>
      <div class="field">
        <label for="sortSelect">Sort by</label>
        <select id="sortSelect">
          <option value="duration_desc">Duration (longest first)</option>
          <option value="duration_asc">Duration (shortest first)</option>
          <option value="start_desc">Start time (newest first)</option>
          <option value="start_asc">Start time (oldest first)</option>
          <option value="status_desc">Build status (worst first)</option>
          <option value="status_asc">Build status (best first)</option>
        </select>
      </div>
      <div class="field">
        <button id="loadButton" onclick="loadBuilds()">Load builds</button>
      </div>
      <button id="themeToggle" class="theme-toggle" type="button">Switch to dark mode</button>
    </div>
    <div class="summary" id="summary"></div>
    <div class="error-banner" id="errorBanner"></div>
  </div>

  <div class="card">
    <table id="buildsTable">
      <colgroup>
        <col data-col="pipeline" />
        <col data-col="branch" />
        <col data-col="build" />
        <col data-col="status" />
        <col data-col="start" />
        <col data-col="duration" />
        <col data-col="link" />
      </colgroup>
      <thead>
        <tr>
          <th>Pipeline</th>
          <th>Branch</th>
          <th>Build #</th>
          <th>Status</th>
          <th>Start Time (UTC)</th>
          <th>Duration (hh:mm:ss)</th>
          <th>Link</th>
        </tr>
      </thead>
      <tbody>
        <!-- Rows inserted by JS -->
      </tbody>
    </table>
  </div>

<script>
let currentBuilds = [];
const columnKeys = ["pipeline", "branch", "build", "status", "start", "duration", "link"];
const defaultColumnWidths = {
  pipeline: 20,
  branch: 18,
  build: 12,
  status: 12,
  start: 20,
  duration: 13,
  link: 5,
};
const columnWidthStorageKey = "dashboard-column-widths";
let columnWidths = { ...defaultColumnWidths };

function loadSavedColumnWidths() {
  try {
    const saved = localStorage.getItem(columnWidthStorageKey);
    if (!saved) return;
    const parsed = JSON.parse(saved);
    columnWidths = { ...columnWidths, ...parsed };
  } catch (err) {
    console.warn("Failed to load saved column widths", err);
  }
}

function persistColumnWidths() {
  try {
    localStorage.setItem(columnWidthStorageKey, JSON.stringify(columnWidths));
  } catch (err) {
    console.warn("Failed to persist column widths", err);
  }
}

function formatDurationHMS(seconds) {
  if (seconds == null) return "";
  seconds = Math.round(seconds);
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const pad = (x) => x.toString().padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

function badgeClass(result) {
  if (!result) return "badge badge-other";
  const r = result.toLowerCase();
  if (r === "succeeded") return "badge badge-success";
  if (r === "failed") return "badge badge-failed";
  return "badge badge-other";
}

function renderTable() {
  const tbody = document.querySelector("#buildsTable tbody");
  tbody.innerHTML = "";

  const pipelineFilter = document.getElementById("pipelineFilter").value.trim().toLowerCase();
  const statusFilter = document.getElementById("statusFilter").value;
  const sortValue = document.getElementById("sortSelect").value;

  let builds = [...currentBuilds];

  if (pipelineFilter) {
    builds = builds.filter(b =>
      (b.pipelineName || "").toLowerCase().includes(pipelineFilter)
    );
  }

  if (statusFilter !== "all") {
    builds = builds.filter(b => {
      const status = (b.result || "").toLowerCase();
      if (statusFilter === "other") {
        return !["succeeded", "partiallysucceeded", "failed", "canceled"].includes(status || "");
      }
      return status === statusFilter;
    });
  }

  // Sorting
  const statusRank = (result) => {
    const normalized = (result || "").toLowerCase();
    const order = ["failed", "canceled", "partiallysucceeded", "succeeded", "other"];
    const mapped = order.includes(normalized) ? normalized : "other";
    return order.indexOf(mapped);
  };

  builds.sort((a, b) => {
    if (sortValue === "duration_desc") {
      return (b.durationSeconds || 0) - (a.durationSeconds || 0);
    } else if (sortValue === "duration_asc") {
      return (a.durationSeconds || 0) - (b.durationSeconds || 0);
    } else if (sortValue === "start_desc") {
      return new Date(b.startTime) - new Date(a.startTime);
    } else if (sortValue === "start_asc") {
      return new Date(a.startTime) - new Date(b.startTime);
    } else if (sortValue === "status_desc") {
      return statusRank(a.result) - statusRank(b.result);
    } else if (sortValue === "status_asc") {
      return statusRank(b.result) - statusRank(a.result);
    }
    return 0;
  });

  for (const b of builds) {
    const tr = document.createElement("tr");

    const pipelineTd = document.createElement("td");
    pipelineTd.textContent = b.pipelineName || "";
    tr.appendChild(pipelineTd);

    const branchTd = document.createElement("td");
    const displayedBranch = b.sourceBranchDisplay || b.sourceBranch || "";
    branchTd.textContent = displayedBranch;
    tr.appendChild(branchTd);

    const buildNumTd = document.createElement("td");
    buildNumTd.textContent = b.buildNumber || "";
    tr.appendChild(buildNumTd);

    const statusTd = document.createElement("td");
    const span = document.createElement("span");
    span.textContent = b.result || "";
    span.className = badgeClass(b.result);
    statusTd.appendChild(span);
    tr.appendChild(statusTd);

    const startTd = document.createElement("td");
    startTd.className = "nowrap";
    startTd.textContent = b.startTime ? new Date(b.startTime).toISOString().replace("Z", "") : "";
    tr.appendChild(startTd);

    const durHMSTd = document.createElement("td");
    durHMSTd.textContent = b.durationSeconds != null ? formatDurationHMS(b.durationSeconds) : "";
    tr.appendChild(durHMSTd);

    const linkTd = document.createElement("td");
    if (b.webUrl) {
      const a = document.createElement("a");
      a.href = b.webUrl;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = "View";
      linkTd.appendChild(a);
    }
    tr.appendChild(linkTd);

    tbody.appendChild(tr);
  }

  const summary = document.getElementById("summary");
  summary.textContent = `Showing ${builds.length} builds (fetched ${currentBuilds.length}).`;
}

async function loadBuilds() {
  const branch = document.getElementById("branchInput").value.trim();
  const daysInput = parseInt(document.getElementById("daysInput").value, 10) || 7;
  const topInput = parseInt(document.getElementById("topInput").value, 10) || 200;
  const days = Math.min(365, Math.max(1, daysInput));
  const top = Math.min(1000, Math.max(1, topInput));
  const errorBanner = document.getElementById("errorBanner");
  errorBanner.style.display = "none";
  errorBanner.textContent = "";

  const btn = document.getElementById("loadButton");
  btn.disabled = true;
  btn.textContent = "Loading...";

  try {
    const params = new URLSearchParams();
    params.append("days", days.toString());
    params.append("top", top.toString());
    if (branch) {
      params.append("branch", branch);
    }

    const res = await fetch(`/api/builds?${params.toString()}`);
    if (!res.ok) {
      const text = await res.text();
      errorBanner.textContent = "Error loading builds: " + text;
      errorBanner.style.display = "block";
      return;
    }
    const data = await res.json();
    currentBuilds = data.builds || [];
    renderTable();
    const summary = document.getElementById("summary");
    summary.textContent = `Fetched ${currentBuilds.length} builds from Azure DevOps (branch filter: ${data.branch || "all"}, lookback: ${data.days} days).`;
  } catch (e) {
    console.error(e);
    errorBanner.textContent = "Unexpected error loading builds. Check the browser console for details.";
    errorBanner.style.display = "block";
  } finally {
    btn.disabled = false;
    btn.textContent = "Load builds";
  }
}

// Re-render table if sort or pipeline filter changes
document.getElementById("sortSelect").addEventListener("change", renderTable);
document.getElementById("pipelineFilter").addEventListener("input", renderTable);
document.getElementById("statusFilter").addEventListener("change", renderTable);

function applyColumnWidths() {
  columnKeys.forEach((key) => {
    const col = document.querySelector(`#buildsTable col[data-col="${key}"]`);
    if (col && columnWidths[key]) {
      col.style.width = columnWidths[key] + "%";
    }
  });
}

function initColumnResizers() {
  const table = document.getElementById("buildsTable");
  const headers = table.querySelectorAll("th");
  headers.forEach((th, index) => {
    const handle = document.createElement("span");
    handle.className = "resizer";
    th.appendChild(handle);
    handle.addEventListener("mousedown", (event) => {
      event.preventDefault();
      const columnKey = columnKeys[index];
      const startX = event.pageX;
      const startWidth = columnWidths[columnKey];
      const tableWidth = table.offsetWidth;
      document.body.classList.add("resizing");

      function onMouseMove(moveEvent) {
        const deltaPx = moveEvent.pageX - startX;
        const deltaPercent = (deltaPx / tableWidth) * 100;
        const newWidth = Math.min(60, Math.max(8, startWidth + deltaPercent));
        columnWidths[columnKey] = newWidth;
        applyColumnWidths();
        persistColumnWidths();
      }

      function onMouseUp() {
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        document.body.classList.remove("resizing");
      }

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });
  });
}

function updateThemeToggleText() {
  const toggle = document.getElementById("themeToggle");
  if (!toggle) return;
  toggle.textContent = document.body.classList.contains("dark") ? "Switch to light mode" : "Switch to dark mode";
}

function initTheme() {
  const saved = localStorage.getItem("dashboard-theme");
  if (saved === "dark") {
    document.body.classList.add("dark");
  }
  updateThemeToggleText();
  const toggle = document.getElementById("themeToggle");
  toggle.addEventListener("click", () => {
    document.body.classList.toggle("dark");
    const mode = document.body.classList.contains("dark") ? "dark" : "light";
    localStorage.setItem("dashboard-theme", mode);
    updateThemeToggleText();
  });
}

loadSavedColumnWidths();
applyColumnWidths();
initColumnResizers();
initTheme();
</script>
</body>
</html>
    """
    return HTMLResponse(content=html)


@app.get("/api/builds")
def get_builds(
    branch: Optional[str] = Query(None, description="Branch name (e.g. 'main' or 'refs/heads/main'). If omitted, all branches."),
    days: int = Query(7, ge=1, le=365, description="Lookback window in days."),
    top: int = Query(200, ge=1, le=1000, description="Max builds to fetch from Azure DevOps."),
):
    """
    Fetch completed builds from Azure DevOps, optionally filtered by branch and time window.
    """
    branch_for_api = None
    wildcard_pattern = None
    if branch:
        normalized = normalize_branch(branch)
        if branch_has_wildcard(branch):
            wildcard_pattern = normalized
        else:
            branch_for_api = normalized

    raw = fetch_builds(branch=branch_for_api, days=days, top=top)
    builds = transform_builds(raw)
    if wildcard_pattern:
        builds = [b for b in builds if fnmatch(b.get("sourceBranch") or "", wildcard_pattern)]
    return JSONResponse(
        {
            "branch": branch,
            "days": days,
            "top": top,
            "count": len(builds),
            "builds": builds,
        }
    )
