# ADO Build Time Dashboard

This web application visualizes Azure DevOps pipeline duration trends so teams can quickly spot regressions, slow builds, and outliers without combing through multiple Azure DevOps pages. By combining pipeline metadata with intuitive filtering, it becomes easy to identify the longest-running builds, compare branches, and monitor optimizations over time.

### Key Features
- **Configurable dashboard:** Filter by branch, pipeline, and date range to tailor the dataset to your investigation.
- **Duration insights:** Sort builds by runtime and compare branches to highlight regressions or improvements.
- **Branch wildcards:** Use wildcard patterns (for example, `release/*`) to focus on groups of related branches.
- **Inline error reporting:** When API requests fail, inline banners surface the issue immediately without blocking alerts.
- **Input validation:** The UI clamps user-provided values to safe ranges so the backend never receives unsupported queries.

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

## Environment Variables
| Environment Variable | Description                                                                                                                                                                                      |
|----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `AZDO_ORG`           | The name of your Azure DevOps Organization. (If you access ADO at `dev.azure.com/yourCompanyNameHere`, then you would use `yourCompanyNameHere` for this value.)                                 |
| `AZDO_PROJECT`       | The name of the project within your Azure DevOps organization containing the pipelines you want to review.                                                                                       |
| `AZDO_PAT`           | A [PAT](https://learn.microsoft.com/en-us/azure/devops/organizations/accounts/use-personal-access-tokens-to-authenticate?view=azure-devops&tabs=Windows) used to authenticate with Azure DevOps. |

### PAT requirements
The PAT used for `AZDO_PAT` needs at least Read permissions on the ADO project being queried.

### Using day-to-day
- To see longest-running builds on main over the last 7 days:
    - Branch: main
    - Days: 7
    - Sort: Duration (longest first)
- To compare branches:
    - Leave Branch blank (all branches)
    - Use the table + Pipeline filter + sort by duration.
- The Branch filter supports wildcards (e.g. `release/*` to include every release branch).
- To focus on a particular service:
    - Pipeline filter: my-service-name substring
- If you hit an error while fetching builds, look for the inline red banner above the table for details.