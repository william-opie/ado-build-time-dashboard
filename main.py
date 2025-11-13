import os
import math
from datetime import datetime, timedelta
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

    # Normalize branch name: allow 'main' or 'refs/heads/main'
    if branch:
        if not branch.startswith("refs/"):
            branch = f"refs/heads/{branch}"
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
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      padding: 1rem 2rem 3rem 2rem;
      background: #f5f5f5;
      color: #222;
    }
    h1 {
      margin-top: 0;
    }
    .card {
      background: #fff;
      border-radius: 12px;
      padding: 1rem 1.5rem;
      box-shadow: 0 2px 8px rgba(0,0,0,0.05);
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
      border: 1px solid #ccc;
      min-width: 160px;
    }
    button {
      padding: 0.5rem 0.9rem;
      border-radius: 6px;
      border: none;
      cursor: pointer;
      background: #2563eb;
      color: #fff;
      font-weight: 600;
    }
    button:disabled {
      opacity: 0.6;
      cursor: default;
    }
    table {
      border-collapse: collapse;
      width: 100%;
      font-size: 0.85rem;
    }
    th, td {
      padding: 0.4rem 0.5rem;
      border-bottom: 1px solid #e5e7eb;
      text-align: left;
    }
    th {
      background: #f9fafb;
    }
    tr:hover {
      background: #f3f4f6;
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
      color: #4b5563;
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
        <label for="branchInput">Branch (e.g. <code>main</code> or <code>refs/heads/main</code>)</label>
        <input id="branchInput" type="text" placeholder="refs/heads/main (blank = all branches)" />
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
        <label for="sortSelect">Sort by</label>
        <select id="sortSelect">
          <option value="duration_desc">Duration (longest first)</option>
          <option value="duration_asc">Duration (shortest first)</option>
          <option value="start_desc">Start time (newest first)</option>
          <option value="start_asc">Start time (oldest first)</option>
        </select>
      </div>
      <div class="field">
        <button id="loadButton" onclick="loadBuilds()">Load builds</button>
      </div>
    </div>
    <div class="summary" id="summary"></div>
    <div class="error-banner" id="errorBanner"></div>
  </div>

  <div class="card">
    <table id="buildsTable">
      <thead>
        <tr>
          <th>Pipeline</th>
          <th>Branch</th>
          <th>Build #</th>
          <th>Status</th>
          <th>Start Time (UTC)</th>
          <th>Duration (min)</th>
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
  const sortValue = document.getElementById("sortSelect").value;

  let builds = [...currentBuilds];

  if (pipelineFilter) {
    builds = builds.filter(b =>
      (b.pipelineName || "").toLowerCase().includes(pipelineFilter)
    );
  }

  // Sorting
  builds.sort((a, b) => {
    if (sortValue === "duration_desc") {
      return (b.durationSeconds || 0) - (a.durationSeconds || 0);
    } else if (sortValue === "duration_asc") {
      return (a.durationSeconds || 0) - (b.durationSeconds || 0);
    } else if (sortValue === "start_desc") {
      return new Date(b.startTime) - new Date(a.startTime);
    } else if (sortValue === "start_asc") {
      return new Date(a.startTime) - new Date(b.startTime);
    }
    return 0;
  });

  for (const b of builds) {
    const tr = document.createElement("tr");

    const pipelineTd = document.createElement("td");
    pipelineTd.textContent = b.pipelineName || "";
    tr.appendChild(pipelineTd);

    const branchTd = document.createElement("td");
    branchTd.textContent = b.sourceBranch || "";
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

    const durMinTd = document.createElement("td");
    durMinTd.textContent = b.durationMinutes != null ? b.durationMinutes.toFixed(2) : "";
    tr.appendChild(durMinTd);

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
    raw = fetch_builds(branch=branch, days=days, top=top)
    builds = transform_builds(raw)
    return JSONResponse(
        {
            "branch": branch,
            "days": days,
            "top": top,
            "count": len(builds),
            "builds": builds,
        }
    )
