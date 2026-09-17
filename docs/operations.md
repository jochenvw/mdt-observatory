# MDT Observatory operations

## Approved topology and deployment gate

This fictional-case demo uses **Bicep + Azure CLI remote builds**, not `azd
deploy`. The parent must complete **azure-validate -> azure-deploy** before any
deployment. `azure.yaml` remains a descriptor; direct deployment bypasses the
required drain protocol.

All application resources use subscription
`e3825c9a-4bce-43e1-899e-1610156c9383`, resource group
`rg-mdt-observatory-demo`, and region `westeurope`. The template also accepts
`swedencentral` for a fresh deployment, but the existing group must not be relocated.

The cloud backend is Blob Storage with the new app's system-managed identity:

| Resource | Configuration |
| --- | --- |
| Container App | `mdt-observatory-vnet`; Multiple mode, exactly one active revision, min=max=1 replica |
| Environment | `cae-mdt-observatory-vnet`; external ingress, customer VNet integration |
| VNet | `vnet-mdt-observatory`, `10.64.0.0/16` |
| ACA subnet | `aca`, `10.64.0.0/23`, delegated to `Microsoft.App/environments` |
| Private endpoint subnet | `private-endpoints`, `10.64.2.0/27` |
| Blob private endpoint | `pe-mdt-observatory-blob`, existing storage account's `blob` subresource |
| Private DNS | `privatelink.blob.core.windows.net`, non-registering `mdt-vnet` link, endpoint DNS zone group |
| Storage | Existing `stmdtgy76frdpub6io`, Standard LRS; public access Disabled, Shared Key false, anonymous blobs false |
| Blob container | `mdt-state`, no anonymous access |
| Registry / telemetry | Existing Basic ACR, `log-mdt-observatory`, `appi-mdt-observatory` |

The /23 ACA subnet exceeds the /27 minimum for workload-profile environments and
does not overlap the separate endpoint subnet or ACA reserved address ranges.
Azure DNS resolves the normal account URL through the private endpoint; do not
replace it with a `privatelink` URL. Storage firewall default is Deny; private
endpoint traffic is authorized separately from the public-endpoint firewall.

Cleanup completed on **2026-09-16**: the old `mdt-observatory` app, its two
managed-identity role assignments and the old `cae-mdt-observatory` environment
are deleted. Verification waited for the environment to disappear from Azure's
resource listing, not merely for the delete command to return.
Legacy Files resources are outside active IaC and are not used by the current app.
Preserve `mdt-observatory-vnet`, its VNet environment, Blob data and all storage
policy restrictions. Incremental deployment alone does not remove omitted
resources. No policy exemption, exclusion tag,
account-key mount or public-storage workaround is part of this design. The
previously generated policy-waiver artifact and execution path have been removed;
no waiver was deployed by the preparation agent.

## Identity and model access

The **new app identity** receives:

- `AcrPull` (`7f951dda-4ed3-4680-a7ca-43fe172d538d`) at the existing registry.
- `Storage Blob Data Contributor` (`ba92f5b4-2d11-453d-a403-e96b0029c9fe`) at the
  `mdt-state` container, not the whole account.
- `Cognitive Services OpenAI User` (`5e0bd9bd-7b93-4f28-af87-19fc36ad61bd`) at
  existing account `nl-stu-jvw-ai-saoyr2` in `nl-stu-jvw-foundry-rg`.

The OpenAI account/deployments are not reconfigured. Endpoint:
`https://nl-stu-jvw-ai-saoyr2.openai.azure.com`; deployment:
`nl-stu-jvw-gpt-6-astra`, existing GlobalStandard capacity 10. The account is in
Sweden, but GlobalStandard inference provides **no regional data-residency
guarantee**. Submit fictional demonstration data only. The legacy identity's two role assignments
have been deleted; the current app's three scoped assignments above remain required.

Runtime settings are:

```text
MDT_STORAGE_BACKEND=azure_blob
MDT_BLOB_ACCOUNT_URL=https://stmdtgy76frdpub6io.blob.core.windows.net
MDT_BLOB_CONTAINER=mdt-state
MDT_SECURE_COOKIE=true
MDT_AZURE_MAX_CONCURRENT_ROLES=3
MDT_AZURE_REQUEST_INTERVAL_SECONDS=20
```

`MDT_PRESENTER_TOKEN` and `APPLICATIONINSIGHTS_CONNECTION_STRING` use ACA secret
references. No Blob account key, SAS, connection string, `/data` mount or Azure
Files binding is supplied to the cloud app. Parent-owned application code selects
managed-identity BlobStore in Azure and retains SQLite for local use. Bootstrap
creates the Blob container, so the app does not need account-wide container-list
permissions.

### Live-role concurrency, pacing and model allocation

The next-case mode selector is independent of the current meeting's mode badge.
An explicit rehearsal/live choice is retained through incoming snapshots and
reconnections; loading a prior live meeting must not switch a chosen rehearsal
back to live. Browser regressions verify the outgoing start-request mode.

These are application settings, not ACA scaling or Foundry allocation changes:

| Deployment flag | Bicep parameter | App environment variable | Default / bounds |
| --- | --- | --- | --- |
| `-AzureMaxConcurrentRoles` | `azureMaxConcurrentRoles` | `MDT_AZURE_MAX_CONCURRENT_ROLES` | 3; integer 1-7 |
| `-AzureRequestIntervalSeconds` | `azureRequestIntervalSeconds` | `MDT_AZURE_REQUEST_INTERVAL_SECONDS` | 20; integer seconds 0-60 |

Up to three independent live role loops may overlap by default. Every model
request and retry still shares the application-wide request pacing and 429
cooldown. The interval is not per role: 20 seconds permits at most approximately
three request starts per minute across the app, before response latency or
cooldowns. Setting zero removes the configured spacing, not the shared 429
cooldown. Role concurrency does not add replicas, Uvicorn workers or independent
state writers; private Blob, identity and drain controls remain unchanged.

Python also accepts finite fractional intervals within 0-60 seconds, but the
deployment interface deliberately accepts whole seconds only. Fractional,
non-finite and out-of-range deployment values are rejected rather than rounded.
The values are serialized as ARM integers and injected as environment strings.
Both the root template and resource module enforce the same bounds/defaults.

Pass settings on the `Release` or `All` invocation that applies infrastructure:

```powershell
.\scripts\deploy.ps1 -Stage Release -Image $image -ValidationApproved `
  -AzureMaxConcurrentRoles 3 -AzureRequestIntervalSeconds 20
```

`Bootstrap` accepts the same parameters, but its placeholder receives no
application environment settings. `Build` and `Drain` do not apply them. These
are explicit release inputs, not values read from the operator's `MDT_*`
environment: omitting the flags on a later release reapplies defaults 3/20.
Changing only these settings needs a new revision through the existing release
gate, not an image rebuild; application-code changes still require a rebuild.

**Parent-reported management snapshot, 2026-09-16:** deployment
`nl-stu-jvw-gpt-6-astra` is GlobalStandard capacity 10, with actual limits of
10 requests per 60 seconds and 10,000 tokens per 60 seconds. Regional quota
`OpenAI.GlobalStandard.gpt-6-astra` reports current usage 10, limit 1,000: nominal
unallocated headroom is 990 allocation units. This is allocation headroom, not
additional throughput already available to this shared deployment, nor a
guarantee of available regional capacity. Other clients consume the deployment's
same request/token budgets.

**Proposed trial only, not approved, changed or verified:** ask the shared model
owner to consider allocation **100**, targeting **100,000 TPM / 100 RPM**, then
trial seven role loops with a reduced two-second interval
(`-AzureMaxConcurrentRoles 7 -AzureRequestIntervalSeconds 2`). This would add
90 allocation units if usage elsewhere remains unchanged. Confirm actual
post-change rate limits before reducing pacing; at two seconds the application
can start at most approximately 30 requests per minute, and large requests,
retries, token estimation or other consumers may still cause throttling. Monitor
429s, latency and token use, and retain the shared cooldown. Until separately
authorized and measured, keep the reproducible defaults 3/20.

No deployment script or template changes the shared model deployment, model
allocation or regional quota. The proposal is an operational recommendation,
not an instruction executed by this configuration.

## Prerequisites

The current case is packaged from the complete clinical dossier in `case.md`;
there is no `case.txt` in this repository. `src/mdt/dossiers/crc_case.json` must
remain included in the Python distribution and container build. The source
academic profile is not an agent identity. External evidence access is recorded
separately from supplied clinical assertions; local protocol access is still
unavailable.

A release never rewrites saved meetings. An earlier-case meeting remains
reviewable/exportable, but cannot be steered, retried or advanced using the new
case runtime. After verifying preserved history, start a new case to activate
the colorectal dossier in the shared room. New snapshots and exports retain
the complete record, all three management alternatives and all eight source
consult contributions; the existing seven app roles and human review gates
remain unchanged.

Use PowerShell 7.2+, authenticated Azure CLI, Bicep and the `containerapp`
extension. Required providers include `Microsoft.Network`, `Microsoft.App`,
`Microsoft.Storage`, `Microsoft.ContainerRegistry`, `Microsoft.Insights`,
`Microsoft.OperationalInsights` and `Microsoft.ManagedIdentity`. Validation must
check regional quota, subnet delegation, private endpoint approval permissions
and permission to assign all three identity roles.

The caller needs deployment/network/storage management permissions and role
assignment permission at the demo scopes and existing OpenAI account. No
governance-exemption permission is needed.

Set `MDT_PRESENTER_TOKEN` to a random 32-512-character value in the process
environment, through the operator's secret-management path. Never print it,
pass it as a command argument or commit it. `Build` and `Drain` need no token.
The app and both lockfiles must be complete, including the new BlobStore code and
its locked dependencies. All uv commands use `--frozen`; remote builds do not
inherit the workstation's `UV_*` settings.

## Non-destructive migration and deployment

The initial migration below is **already completed**. It documents initialization
of the replacement topology, not an instruction to bootstrap the running app
again. For future updates, validate first, then run only `Build` and `Release`.
The initial sequence, run from `C:\_CODE\mbt_vision` with the token inherited, was:

```powershell
.\scripts\deploy.ps1 -ValidationApproved -Stage Bootstrap -Location westeurope
$image = .\scripts\deploy.ps1 -ValidationApproved -Stage Build -Location westeurope
.\scripts\deploy.ps1 -ValidationApproved -Stage Release -Image $image -Location westeurope
```

Alternatively, `-Stage All` executes this sequence. Defaults are `All`,
`westeurope`, and the subscription above. `-Image` is required only for `Release`
and must be an immutable `mdt-observatory@sha256:...` digest in the demo registry.
App/environment names are fixed to the replacement names shown above.

1. **Bootstrap:** when the legacy app is present, switches it to Multiple mode, deactivates every
   legacy revision and waits for zero replicas/no active revisions **before**
   creating the new app. It retains all old resources. Bicep creates networking,
   the Blob container, a private placeholder app and three role assignments for
   the new identity. The placeholder receives no app secrets or storage settings.
2. **Build:** ACR Tasks builds Node 22/Vite and Python 3.12 remotely, with locked
   `npm ci` and `uv sync --frozen --no-dev`. No local Docker engine is required.
   The runtime retains editable `/app/src/mdt` and `/app/frontend/dist`, runs as
   UID/GID 10001 and starts one Uvicorn process on port 8000. Build never drains
   the running application.
3. **Release:** checks private-storage metadata, drains the legacy app if present,
   switches the replacement to Multiple mode, and drains all replacement
   revisions. It deploys the immutable image with a unique revision suffix and
   explicit named-revision traffic. Only the new revision is activated/served.
   Unexpected old writers cause all replacement revisions to be stopped.
4. **Verify:** checks private endpoint approval, DNS linkage, storage restrictions,
   Blob backend settings, no mounts, TLS, health/readiness, frontend HTML, API
   authentication, one healthy active replica and no running legacy app.

An old SMB-only image is **not** suitable for the Blob deployment. Build the
parent's completed BlobStore code, even though infrastructure changes themselves
do not change an image. Bootstrap refuses to overwrite an existing real
replacement app; repeat `Build`/`Release` for later updates.

For maintenance:

```powershell
.\scripts\deploy.ps1 -Stage Drain -ValidationApproved
```

This drains both legacy and replacement apps when present. Single mode is never
used: it can revive the previous ready revision while a new one starts. The
explicit drain creates an intentional outage. Do not deploy concurrently, enable
extra replicas/workers, activate old revisions manually or use plain `azd deploy`.
Rollback uses `Release` with a compatible prior Blob-backed image; there is no
automatic rollback or SQLite-to-Blob migration. Preserve old data until a separate
data migration/cleanup is approved.

The script writes secure Bicep parameters into a randomly named owner-only
temporary directory and removes it in `finally`. ARM outputs do not contain
secrets. Do not use CLI debug output or shell transcripts. A forcibly killed
process may leave its restricted temporary directory; remove only the exact
identified directory, never a wildcard or the temp root.

## Verification and operational limits

```powershell
.\scripts\verify-azure.ps1 -TimeoutSeconds 300
```

The timeout accepts 10-1800 seconds. `/healthz` and `/readyz` are public;
patient-data reads/writes/exports/streams require the presenter HttpOnly cookie.
With the token present, verification checks `/api/auth`, Secure/HttpOnly/
SameSite=Strict attributes and an authenticated read. Without it, that part is
explicitly skipped. Verification never changes a meeting.

Management-plane metadata proves configuration, not data-plane connectivity.
`/readyz` lists the Blob container through managed identity, exercising storage,
RBAC and DNS; `/healthz` does not access the database. The cloud acceptance below
has passed. Future releases must still verify actual Blob readiness and the
application workflow; repeat private DNS checks inside the environment when
networking changes. The workstation is not inside the VNet and should not gain
public Blob access. Role propagation can take several minutes; report
authorization failures rather than falling back to SQLite or rehearsal.

### Recorded cloud acceptance: 2026-09-16

The parent verified live-model meeting
`4f675568-da0a-4d2e-ae31-ff18af310432` reached `DECISION_CAPTURED` with seven roles,
228 events and no fallback. Restarting the actual active revision preserved the
authenticated latest meeting and complete decision export byte-for-byte, checked
only after the original replica was absent and exactly one healthy replacement
remained.

`artifacts\cloud-restart-proof.json` records the old/new replica names and the
decision-export SHA-256:

```text
0D11FAB8E6305854E51DF929A2950B6679EC0BA838030EFCC75B5ACB60AC08AE
```

Application Insights verification included model, tool, role and persistence
spans, model request/token metadata, `mdt.events` metrics and this meeting's
`CaseClosed` log. These are recorded parent-run acceptance results, not a claim
that verification was rerun during this documentation update.

### Safe restart verification

Use this procedure only for an **idle `DECISION_CAPTURED` meeting**, with no
concurrent presenter, active agent work, pending retry, deployment or state
mutation. It is a persistence check, not an availability test during live work.

1. Authenticate through `/api/auth`. Record the latest meeting ID, capture the
   complete decision export as raw bytes and calculate its SHA-256. Record the
   active revision and every original replica name; require one healthy active
   revision and one replica before proceeding.
2. Restart that active revision through the approved operational workflow. Do
   not activate an old revision, change traffic, scale out or alter storage/network
   policy for this check.
3. Poll revision/replica status with a finite timeout. Wait until **every original
   replica name is absent** and **exactly one healthy, ready replacement replica**
   remains on the expected active revision. Then require `/readyz` to succeed.
   A healthy URL or unchanged export while the old replica still exists is not
   restart evidence. On timeout or an unexpected replica count, stop and report
   the check as incomplete rather than comparing against a possibly old process.
4. Authenticate again if necessary, retrieve the latest meeting and require the
   original ID. Retrieve its **complete** decision export and compare raw bytes
   and SHA-256 with the pre-restart copy; do not compare only a summary, event
   count or normalized JSON.
5. Record the old/new replica names, readiness result, meeting ID, export hashes
   and byte-comparison result in the proof artifact. Resume presenter activity
   only after verification completes.

Voting commands `/concur` and `/object` require the integer `plan_version` from
the current meeting's `plan.version`. Re-fetch after plan changes.

Application Insights uses service name `mdt-observatory`; instrumentation must
exclude token values and prompt/patient bodies. Check `AppRequests`,
`AppDependencies` and `AppTraces` after the walkthrough, allowing ingestion delay:

```kusto
AppRequests
| where TimeGenerated > ago(30m) and AppRoleName == "mdt-observatory"
| summarize Requests=count(), Failures=countif(Success == false) by Name
```

Seven-day Blob/container soft deletion is configured; it is not a complete
backup or concurrency strategy. The parent-owned BlobStore must implement its
documented versioning/concurrency behavior. Network/endpoint/DNS charges and ACA
managed networking resources are additional to the always-on replica, registry,
storage and logging. These costs are justified by the actual private-storage
policy requirement. Existing drained environments and old resources can still
incur charges; cleanup needs separate approval.

Outputs include the replacement app URL/FQDN/name/identity, environment ID,
registry, telemetry workspace, storage account, Blob container/account URL, VNet
ID and Blob private endpoint ID. The script prints non-secret outputs but does
not persist them into AZD settings.

## References

- [ACA custom VNet and delegated subnet requirements](https://learn.microsoft.com/azure/container-apps/custom-virtual-networks)
- [Storage private endpoints and DNS](https://learn.microsoft.com/azure/storage/common/storage-private-endpoints)
- [ACA revision modes](https://learn.microsoft.com/azure/container-apps/revisions)
- [Private endpoint Bicep schema](https://learn.microsoft.com/azure/templates/microsoft.network/2024-05-01/privateendpoints)
