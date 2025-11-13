# Quick Start

Build:
```bash
docker build -t ado-pipeline-runtime-dashboard .
```

Run (example):

```bash
docker run \
  -e AZDO_ORG="myorg" \
  -e AZDO_PROJECT="MyProject" \
  -e AZDO_PAT="your_pat_here" \
  -p 8000:8000 \
  ado-pipeline-runtime-dashboard
```

Then open:
http://localhost:8000

### PAT requirements
Your `AZDO_PAT` should at minimum Read permission on the project(s) you care about.

### Using day-to-day
- To see longest-running builds on main over the last 7 days:
    - Branch: main (or refs/heads/main)
    - Days: 7
    - Sort: Duration (longest first)
- To compare branches:
    - Leave Branch blank (all branches)
    - Use the table + Pipeline filter + sort by duration.
- To focus on a particular service:
    - Pipeline filter: my-service-name substring