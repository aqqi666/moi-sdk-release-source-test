# MOI Product Go SDK

Go SDK for UI-visible MOI product APIs.

The existing `MemoryService` / `ConsumerMemoryHandle` target the legacy Consumer Memory/Profile API. Current MOI does not expose those routes; these entries are not a current capability. See [Legacy API availability](../docs/product-sdk-capabilities.md#legacy-api-availability).

Typed product result objects are generated from `../proto/product/*.proto`.

`Client.Runners(workspaceID)` and `Client.Sandboxes(workspaceID)` are also exposed
through CLI `runner` and `sandbox` HTTP commands, including typed network/quota
updates and explicit admin targets. Connection credential issuance is separate
from opening a terminal. `ConnectTerminal` / `connect_terminal` use binary stdin and text resize frames; the CLI `sandbox connect-terminal` command performs a connection probe. See [Runner and sandbox HTTP alignment](../docs/product-sdk-capabilities.md#runner-and-sandbox-http-alignment).

`Error.Details` uses `sdk.ErrorDetails` (`map[string]any`) and preserves nested
objects and lists. JSON numbers use `json.Number`, including large resource IDs.
Go callers constructing errors should use `sdk.ErrorDetails` or `map[string]any`
instead of `map[string]string`; read string diagnostics with a type assertion
and check presence. See [Structured error details](../docs/product-sdk-capabilities.md#structured-error-details).

File imports may omit the task name and target volume; MOI supplies an absent name. `ImportTaskCreateSpec.TaskID` and `FileImportTaskSpec.TaskID` optionally pass a caller-selected task ID unchanged. `ImportTaskUpdateSpec` edits the name, load mode, file filter and URIs; choose the target volume at creation. Export tasks require a name and accept the optional `Creator` label.

`KnowledgeService.CreateWithSources` accepts `WithSemanticModelWithSourcesTargetCatalogID` to choose the destination Catalog and `WithSemanticModelWithSourcesSourceSelections` to select existing Catalog files or tables. The CLI exposes `--target-catalog-id` and `--source-selections-file`; use `moi-cli schema semantic-model create-with-sources --argument source-selections-file` for the file structure.

`KnowledgeService.AppendSources` also accepts Catalog selections through `WithSemanticModelAppendSourceSelections`; the CLI exposes `semantic-model append-sources --source-selections-file`. Knowledge creation exposes descriptions and the image-index setting, while `semantic-model update` accepts `--description`, `--tables-file` and `--files-file` to pass the corresponding Go SDK options.

Catalog tree navigation supports pagination, search, resource types and exact resource IDs. `WithCatalogTreeTableLeaves(false)` excludes table leaves while omission keeps the server default. The CLI exposes these through `catalog tree`, `system-tree` and `database-table-leaves`; `catalog search-data-dashboard-tables` exposes permission-scoped table search across databases.

Compute creation and updates accept `WithComputeKind` / `WithComputeUpdateKind` and `WithComputePyRequirementsTxt` / `WithComputeUpdatePyRequirementsTxt`. Spec creation and updates accept node placement through `WithComputeSpecNodePlacement` / `WithComputeSpecUpdateNodePlacement`. See [Compute configuration](../docs/product-sdk-capabilities.md#compute-configuration) for CLI flags, clearing behavior and dependency observations.

Knowledge creation accepts `KnowledgeService.CreateWithSpec` with `SemanticModelCreateSpec` for embedding preservation and drawing settings. Keep description, tables and files in the existing options. See [Knowledge creation controls](../docs/product-sdk-capabilities.md#knowledge-creation-controls) for omission, explicit false and CLI usage.

Workflow template creation and updates expose key, description, input-form and builtin options in the CLI. MOWL templates have a dedicated update method and handle operation. Template response IDs use the handler’s 64-bit range. See [Workflow template controls](../docs/product-sdk-capabilities.md#workflow-template-controls).

## Current IAM capabilities

The existing IAM service accepts optional capability IDs:

```go
capabilities, err := workspace.IAM().CurrentPrincipalCapabilities(ctx, "action.role.create", "navigation.roles")
```

Omit IDs to retrieve the full projection. The server evaluates only supported requested IDs and returns the existing metadata, denial reasons and resource scopes in capability ID order. Unknown IDs, including empty values, are reported in `capabilities.GetUnsupportedCapabilityIds()` with HTTP 200. If all IDs are unsupported, `items` is empty; duplicate IDs are returned once. The SDK sends IDs unchanged. See the [API contract](../../docs/iam/07-public-api-frontend-sdk-contracts.md#21-按-id-查询当前主体-capability).

## A2A message/send semantics

The server answers `message/send` at task admission (A2A 0.3 non-blocking default): a still-running task returns its persisted non-terminal projection (`kind=task`, `status.state` of `submitted` or `working`, with `metadata.eventCursor`), while a task settled inside the admission window keeps its terminal or acknowledgement answer unchanged. `configuration.blocking: true` is explicitly rejected with HTTP 400, JSON-RPC `-32602`, and `error.data.reason = BLOCKING_UNSUPPORTED`; other `configuration` keys are ignored.

`AgentService.A2A` and `AgentHandle.SendText` keep their signatures: when a send result is a non-terminal task, the SDK internally follows it to a terminal state before returning — first through `tasks/resubscribe` resuming at the persisted `eventCursor` (bounded reconnects with backoff), degrading to `tasks/get` polling every 2 seconds when the stream cannot be held. Message-kind results (feedback ack, run-control ack, provider interaction) and already-terminal tasks pass through unchanged. The terminal set is `completed`/`failed`/`canceled`/`rejected` plus the interrupted `input-required`/`auth-required` states, which are handed back to the caller for handling.

`WithA2AWaitTimeout` bounds the whole follow (default 10 minutes) and is independent of the per-request `WithTimeout`. When the budget is exhausted the call returns `ErrTimeout` carrying the task id, so the caller can resume the persisted task explicitly instead of treating it as lost.

## UC Personal Access Token

For product APIs, construct the client with `NewWithPersonalAccessToken`. The
opaque PAT is sent only as `X-API-Key`; the product endpoint still includes its
environment-specific `/newmoi` base path.

```go
client, err := sdk.NewWithPersonalAccessToken(
	"http://127.0.0.1:19050/newmoi",
	"your-personal-access-token",
)
```

The PAT identifies the human user; it does not fix a workspace or Role. To
select a current Role for a workspace, add a workspace-scoped option:

```go
client, err := sdk.NewWithPersonalAccessToken(
	"http://127.0.0.1:19050/newmoi",
	"your-personal-access-token",
	sdk.WithWorkspaceCurrentRoleID("workspace-a", "12"),
	sdk.WithWorkspaceCurrentRoleID("workspace-b", "27"),
)
```

`roleID` must be the canonical positive decimal `int64` form. It is an
untrusted Role Candidate: Backend and Core still verify that it is a current,
direct binding for the PAT user in the request workspace before producing the
single Effective Role. If no Role is selected for a workspace, Backend uses the
user's Default Role. Invalid, unbound, cross-workspace, or disabled Roles are
rejected without falling back to the Default Role.

Workspace current Role options are immutable after client construction.
`X-Workspace-ID` and `X-MOI-Role-ID` are SDK-reserved headers: after generic
custom headers/request modifiers run, the HTTP request finalizer removes every
case variant, restores the request workspace, and adds a Role only from the
matching typed mapping. Without a typed mapping, other custom-header and
request-modifier behavior is preserved, but a generic Role header is removed and
Backend uses the Default Role. WebSocket query headers apply the same reserved
header binding after custom headers and do not run HTTP request modifiers.

`SQLService.QueryWebSocketHeaders` and
`SQLService.QueryWebSocketSubprotocols` return credential-bearing handshake
material, including the PAT. Consume these values only while creating the
WebSocket connection in-process; never log, display, or persist them.

For task-to-entry-point guidance, start with the [AI Decision Ladder](../docs/product-sdk-capabilities.md#ai-decision-ladder), then use the [User Story Matrix](../docs/product-sdk-capabilities.md#user-story-matrix), [AI Task Selection Guide](../docs/product-sdk-capabilities.md#ai-task-selection-guide), [AI Intent Disambiguation Matrix](../docs/product-sdk-capabilities.md#ai-intent-disambiguation-matrix), and [User Context Entry Matrix](../docs/product-sdk-capabilities.md#user-context-entry-matrix) before dropping to route-aligned services directly. Use the [Capability Area Promotion Map](../docs/product-sdk-capabilities.md#capability-area-promotion-map), [Route-Aligned Service Promotion Map](../docs/product-sdk-capabilities.md#route-aligned-service-promotion-map), and [Backend API Promotion Checklist](../docs/product-sdk-capabilities.md#backend-api-promotion-checklist) when adding or changing product APIs. When a handle needs an existing id, use the [Handle ID Source Matrix](../docs/product-sdk-capabilities.md#handle-id-source-matrix) before writing the constructor call.

AI usage contract:

AI decision ladder:

- Classify the requested product outcome first; use Cross-Domain User Journeys before task rows when the request spans multiple product areas.
- Resolve ambiguous wording with the AI Intent Disambiguation Matrix; ask for explicit user choice when the source or outcome remains unclear.
- Choose the SDK starting object from the User Context Entry Matrix using only supplied context, typed SDK results, UI state, or documented discovery/create calls.
- Select the promoted User Story Matrix row and minimal handle/spec path from the User Story Ergonomic Usage Tiers.
- Verify every existing id with the Handle ID Source Matrix before binding handles.
- Check the detailed safety matrices needed by the selected lifecycle step before polling, retrying, deleting, sharing, displaying, or automating SDK calls.
- Use route-aligned services only when no promoted user-story facade covers the requested outcome or explicit route-level control is required; keep that choice out of friendly SDK examples.

1. Match the user request to the Task quick start table, AI Task Selection Guide, or User Story Matrix before choosing an SDK method.
2. Use the AI Intent Disambiguation Matrix when a request could match multiple promoted tasks or a route-aligned escape hatch; ask for explicit user choice if the source or outcome remains ambiguous.
3. Use the User Context Entry Matrix to choose the SDK starting object from the context already available; if required context is missing, ask for explicit user input or use the documented discover/create path before binding handles.
4. Check the User Story Ergonomic Usage Tiers before writing code; start with the minimal path, add advanced control only when the user asks or interaction mode requires it, and use escape boundaries only for uncovered route-level behavior.
5. Check the User Story Operation Intent Coverage before assuming a task supports a lifecycle action; each task must state its read/discover, create/configure, update/action, delete/cancel, and observe/result behavior or say the action is not promoted.
6. Check the User Story Capability Availability Coverage before choosing method names; the matched task must state availability probe, unavailable signal, required dependency/configuration, forbidden availability workaround, and AI-safe unavailable behavior.
7. Check the User Story Abstraction Fitness before choosing method names; each task must state the user mental model, friendly handle/spec shape, hidden route/scope details, caller-owned boundary, and forbidden low-level shortcut.
8. If the request spans multiple product areas, choose the Cross-Domain User Journeys outcome first, then follow the User Story Flow Recipes for each matched task before writing code; they define the ordered start point, next calls, produced handles/results, and source rules.
9. Check the User Story State Handoff Coverage before passing values between SDK calls; the matched task must state carried typed state, public accessor/result source, next-call binding, forbidden handoff shortcut, and AI-safe handoff behavior.
10. Check the Cross-Domain Journey Example Anchors before copying README example lines for a multi-area outcome.
11. Check the Cross-Domain Journey Risk Coverage before composing retries, cancellations, reruns, permission-sensitive operations, or external dependency calls across product areas.
12. Check the User Story Discovery and Selection Coverage before constructing handles from ids; it identifies the promoted discover/create path and when route-aligned fallback is not a promoted discovery path.
13. Check the User Story Selection Disambiguation Coverage before selecting one resource from list, search, name, or paginated results; the matched task must state selection input, uniqueness rule, pagination/search boundary, ambiguous/missing selection handling, and forbidden selection shortcut.
14. Check the User Story Ordering and Recency Coverage before honoring latest, recent, oldest, first, top, sorted, priority, or time-window wording; the matched task must state ordering intent, authoritative order source, recency/time-window source, forbidden ordering shortcut, and AI-safe ordering behavior.
15. Check the User Story Outcome Contracts before treating a task as complete; confirm the user-visible outcome, continuation handle/spec, and caller-owned inputs or decisions.
16. Check the User Story Interaction Mode Coverage before writing code that polls, streams, paginates, batches, deletes, cancels, forces, or asks for approval.
17. Check the User Story Execution Budget Coverage before polling, streaming, paginating, retrying, or waiting on long-running work; the matched task must state timeout/deadline source, polling/stream stop condition, page/batch limit, retry budget, and approval/escalation boundary.
18. Check the User Story Pagination and Partial Result Coverage before treating first pages, previews, streams, batches, or capped reads as complete; the matched task must state paginated/partial surfaces, continuation token/source, complete-result proof, forbidden partial-result shortcut, and AI-safe pagination behavior.
19. Check the User Story Error Recovery Coverage before adding retries, reruns, prompts, or fallback behavior; the matched task must state retryable failures, user-correctable failures, forbidden recovery, and the AI-safe next action.
20. Check the User Story Permission and Scope Coverage before issuing permission-sensitive calls; the matched task must state product scope, permission-sensitive operations, caller-owned authorization boundary, forbidden scope/RBAC behavior, and AI-safe permission handling.
21. Check the User Story Ownership and Collaboration Coverage before modifying, exposing, deleting, sharing, or continuing work on resources in a shared workspace; the matched task must state ownership evidence, collaborator/shared scope, caller-owned decision boundary, forbidden cross-user shortcut, and AI-safe collaboration behavior.
22. Check the User Story Input Construction Coverage before constructing specs, options, enum values, secrets, or payloads; the matched task must state required caller inputs, derived typed-result inputs, option/enum/secret rules, forbidden construction behavior, and AI-safe construction.
23. Check the User Story Value Format and Units Coverage before serializing identifiers, timestamps, durations, byte sizes, limits, enum values, URLs, SQL, cron, or payload fields; the matched task must state value/format contract, unit/timezone authority, enum/identifier format, forbidden format shortcut, and AI-safe value behavior.
24. Check the User Story Default and Omission Coverage before relying on omitted fields, empty values, zero values, or backend defaults; the matched task must state optional omissions, invalid empty/zero values, backend/default authority, forbidden defaulting behavior, and AI-safe omission behavior.
25. Check the User Story Completion Verification Coverage before treating a write, async start, delete, cancel, or error-only method as complete; the matched task must state completion signal, verification call, async/delete/cancel handling, forbidden completion shortcut, and AI-safe stop condition.
26. Check the User Story Result Accessor Coverage before reading returned values; the matched task must state public result/accessor source, user-readable fields, continuation fields, forbidden extraction shortcut, and AI-safe accessor behavior.
27. Check the User Story Output Consumption Coverage before displaying or reusing returned values; the matched task must state user-facing output, continuation output, sensitive/internal output boundary, forbidden output consumption, and AI-safe consumption behavior.
28. Check the User Story Sensitive Data Handling Coverage before logging, persisting, showing examples, or passing SDK inputs/outputs into AI context; the matched task must state sensitive inputs, sensitive outputs, logging/example boundary, persistence/AI-context boundary, and AI-safe handling.
29. Check the User Story Automation Safety Coverage before repeating or automating SDK calls; the matched task must state repeat-safe behavior, idempotency key or lookup, external/cost side-effect boundary, forbidden automation shortcut, and AI-safe automation behavior.
30. Check the User Story Concurrent Submission Coverage before allowing parallel SDK calls, UI double-clicks, background polls, async retries, or multiple AI workers to act on the same task; the matched task must state operation identity, parallel-safe reads, serialized mutation boundary, forbidden duplicate submission, and AI-safe in-flight behavior.
31. Check the User Story Impact Assessment Coverage before asking for confirmation or executing high-impact SDK operations; the matched task must state impact source, affected scope, cost/external side effects, uncertainty boundary, and AI-safe impact summary.
32. Check the User Story Confirmation and Preview Coverage before destructive, cost-incurring, external, data-moving, permission-changing, or irreversible SDK operations; the matched task must state confirmation trigger, preview/preflight source, user-visible confirmation summary, forbidden implicit approval, and AI-safe confirmation behavior.
33. Check the User Story Abort and Cleanup Coverage before abandoning, canceling, compensating, or cleaning up partial SDK work; the matched task must state abort trigger, cleanup/compensation target, state proof before cleanup, forbidden rollback shortcut, and AI-safe abort behavior.
34. Check the User Story Progress Visibility Coverage before waiting on, streaming, paginating, batching, deleting, canceling, or otherwise monitoring SDK work; the matched task must state progress signal, status/read call, user-visible update, forbidden silent wait, and AI-safe progress reporting.
35. Check the User Story Diagnostic Handoff Coverage before asking a user, support engineer, or later AI step to debug a failed, stuck, or ambiguous task; the matched task must state safe diagnostic context, correlation/status handle, sensitive diagnostic boundary, forbidden diagnostic shortcut, and AI-safe diagnostic handoff.
36. Check the User Story Freshness and Conflict Coverage before updating, deleting, canceling, rerunning, publishing, or otherwise acting on previously read state; the matched task must state fresh-state source, conflict/stale signal, destructive/update conflict boundary, forbidden stale-state shortcut, and AI-safe conflict handling.
37. Check the User Story Stability Evidence before writing code; the matched task must list Go/Python facade tests, stable proof, and failure boundary.
38. Check the User Story Representative Method Coverage before writing examples; the matched task must have visible Go/Python calls that mirror the language README examples.
39. Check the User Story Example Scenario Coverage before adapting examples; the matched task must state user scenario, copyable example anchor, inputs to replace, expected user-visible output, and AI adaptation boundary.
40. Bootstrap through the product endpoint, then use `EnsureWorkspace` for name-based find/create or `Workspace` only for an already sourced workspace id before continuing with `WorkspaceHandle` for workspace-scoped tasks.
41. Prefer the listed handle/spec entry points whenever they exist; do not start from `client.<domain>(workspaceID)` for a promoted user task.
42. Use route-aligned services only as an explicit escape hatch for domains without a promoted user-story facade or when route-level control is required.
43. Do not expose the Apps backend domain through the Go Product SDK, including `/apps`, `/apps/:app_code`, or app-specific workflows.
44. When a handle requires an existing id, obtain that id from a typed SDK create/list/get result, a UI-selected resource, or explicit user input; handle constructors only bind existing resources and do not create or discover them; do not invent ids or infer them from `ProductData`.
47. Treat error-only write methods as success/failure checks only; they do not return product data, ids, or handles and must not be used as the source for the next SDK call.

Task quick start:

Use the [Cross-Domain User Journeys](../docs/product-sdk-capabilities.md#cross-domain-user-journeys) first when the request spans multiple product areas. Then use the [AI Task Selection Guide](../docs/product-sdk-capabilities.md#ai-task-selection-guide) for intent signals and avoid rules before applying this table. Use the [AI Intent Disambiguation Matrix](../docs/product-sdk-capabilities.md#ai-intent-disambiguation-matrix) when wording could match multiple tasks or a route-aligned escape hatch. Use the [User Context Entry Matrix](../docs/product-sdk-capabilities.md#user-context-entry-matrix) to choose the SDK starting object from the context already available. Check the [User Story Ergonomic Usage Tiers](../docs/product-sdk-capabilities.md#user-story-ergonomic-usage-tiers) so examples start with the minimal path and add advanced control only when needed. Check the [User Story Operation Intent Coverage](../docs/product-sdk-capabilities.md#user-story-operation-intent-coverage) before adding lifecycle actions such as create/configure, update/action, delete/cancel, or observe/result. Check the [User Story Capability Availability Coverage](../docs/product-sdk-capabilities.md#user-story-capability-availability-coverage) before choosing method names. Check the [User Story Abstraction Fitness](../docs/product-sdk-capabilities.md#user-story-abstraction-fitness) before picking handles or specs so the code follows the user mental model instead of route-group translation. After choosing a row, follow its [User Story Flow Recipe](../docs/product-sdk-capabilities.md#user-story-flow-recipes) before writing code. Check the [User Story State Handoff Coverage](../docs/product-sdk-capabilities.md#user-story-state-handoff-coverage) before passing values between SDK calls. Check the [Cross-Domain Journey Risk Coverage](../docs/product-sdk-capabilities.md#cross-domain-journey-risk-coverage) before composing retries, cancellations, reruns, permission-sensitive operations, or external dependency calls. Check the [User Story Discovery and Selection Coverage](../docs/product-sdk-capabilities.md#user-story-discovery-and-selection-coverage) before constructing handles from ids. Check the [User Story Selection Disambiguation Coverage](../docs/product-sdk-capabilities.md#user-story-selection-disambiguation-coverage) before selecting one resource from list, search, name, or paginated results. Then check the [User Story Outcome Contract](../docs/product-sdk-capabilities.md#user-story-outcome-contracts) so generated code stops at a user-visible result and keeps caller-owned inputs explicit.

| User task | Prefer |
|-----------|--------|
| Bootstrap a UI workspace and inspect identity | `Client.EnsureWorkspace`, `Client.Workspace`, `WorkspaceHandle` |
| Manage workspace members | `WorkspaceMemberHandle` |
| Browse catalog resources and operate tables | `CatalogHandle`, `DatabaseHandle`, `TableHandle`, `TableColumn` |
| Manage volumes, folders, and files | `VolumeHandle`, `FolderHandle`, `FileHandle`, `UploadedFilePreview`, `ConnectorFileHandle` |
| Deploy, run, inspect, rerun, and cancel workflows | `WorkflowHandle`, `WorkflowRunHandle`, `WorkflowRunNodeHandle`, `WorkflowRunRerunHandle` |
| Design workflow custom operators and templates | `CustomOperatorHandle`, `CustomOperatorSpec`, `CustomOperatorTestInput`, `WorkflowTemplateHandle` |
| Publish and invoke WorkItem API services | `WorkitemAPIServiceHandle`, `WorkitemAPIServicePublishSpec`, `WorkitemAPIServiceInvokeSpec` |
| Review lineage artifacts and rerun from nodes/blocks | `ArtifactHandle`, `ArtifactBlockHandle`, `ArtifactNodeHandle`, `ArtifactNodeBlockHandle`, `LineageRevisionSwitch` |
| Ask Explore questions with selected sources | `ExploreSessionHandle`, `ExploreMessageHandle`, `ExploreDataSources` |
| Browse Explore source tables and columns | `ExploreDataHandle`, `ExploreDatabaseHandle`, `ExploreTableHandle` |
| Manage semantic models and entries | `SemanticModelHandle`, `SemanticEntryHandle`, `SemanticEntryInput` |
| Manage connectors plus import/export tasks | `ConnectorHandle`, `FileImportTaskSpec`, `ImportTaskUpdateSpec`, `ExportTaskSpec`, `ExportTaskConfig`, `ExportTaskFile`, `ImportTaskHandle`, `ExportTaskHandle` |
| Use product agents through A2A | `AgentHandle`, `AgentTextMessage`, `AgentTaskRequest`, `AgentInputSubmission` |
| Configure model providers and routers | `ModelProviderHandle`, `ProviderBackendHandle`, `ProviderRouterHandle` |
| Manage compute resources | `ComputeResourceHandle` |
| Publish and subscribe data shares | `DataSharePublishHandle`, `DataShareSubscriptionHandle` |
| Work in the SQL editor and query history | `SQLMetadataHandle`, `SQLDatabaseMetadataHandle`, `SQLTableMetadataHandle`, `SQLWorkbookHandle`, `SQLWorkbookVersionHandle`, `SQLQueryHandle`, `SQLStatementHandle` |

Endpoint rule:

- Product Go SDK clients use the same product API gateway and RBAC layer used by the MOI UI.
- Local SDK development and integration tests may use `moi-backend` directly when no product gateway is running.
- `moi-backend` must support user-scoped API key authentication for SDK calls, not only UI token/session authentication.
- Product Go SDK clients must not use `moi-core/catalog` as their default endpoint.
- Direct catalog access belongs to core SDKs, backend internals, or test diagnostics, not to Product SDK actions.

Gate meaning:

- Route alignment proves required backend product routes are reachable from Go and Python SDK services.
- Route alignment uses the runtime Gin route manifest from `moi-backend/cmd/sdk-route-manifest` and fails when a required backend product route has no Go and Python SDK route mapping.
- Capability maturity proves known SDK methods do not regress into raw request/response shapes without an explicit design exemption.
- User-story facade alignment proves promoted task-level handle/spec APIs are present in both Go and Python SDKs, remain cross-language compatible, and do not regress into route-only or raw request/response shapes.
- It checks Go/Python promoted handle methods and direct `Client` user-story entries for compatible parameter names, parameter shapes, and return shapes so user-facing snippets transfer across languages.
- It checks promoted builder objects such as `ExploreDataSources` for cross-language method, parameter, and return-shape parity.
- It also checks option helpers used by promoted handle option families for Go/Python counterparts, compatible parameter names and shapes, and Python package-root exports.
- It checks option helpers remain modifiers of already selected `Client` or handle calls, not user-story SDK entry points, AI task-selection sources, or standalone copy anchors.
- It checks A2A protocol constants and low-level request types remain explicit protocol-control values, not user-story SDK entry points, AI task-selection sources, or standalone copy anchors.
- It checks SDK error types, helpers, and sentinel values remain diagnostic/error-branch values, not user-story SDK entry points, AI task-selection sources, recovery-strategy sources, input-construction sources, or standalone copy anchors.
- It checks local file path upload helpers remain caller-supplied file input conveniences, not AI file-discovery, local-filesystem probing, filename-inference, default upload entry points, or standalone copy anchors.
- It also checks Go/Python promoted spec, input, message, request, submission, and config fields for parity so examples and AI-written code do not drift at the object-construction boundary.
- It checks User Story Gap Register rows keep non-promoted route-aligned gaps out of every user-friendly SDK section.
- It checks route-aligned `sdk_method` entries stay route coverage facts, not AI copy anchors, until user-story handle/spec evidence promotes the outcome.
- Route mapping metadata is for alignment gates and diagnostics only; it is not a user-story SDK entry point, AI task-selection source, or example anchor.
- Passing route alignment alone does not prove a new backend API has a high-level user-story SDK. New user-facing tasks need Go/Python facade entries with compatible parameter names, parameter shapes, return shapes, and promoted input fields before they are considered promoted.
- The gate does not parse README snippets or Example task index Replace/Result/source columns to prove documentation variable completeness.

Minimal Go bootstrap:

`productEndpoint` must include the environment's product API base path, for
example `https://example.com/newmoi` or another environment-specific prefix.
The SDK appends product-relative paths to that address and does not add
`/newmoi` itself.

`go
package main

import (
 "context"
 "time"

 sdk "github.com/matrixorigin/matrixflow/sdk/go-sdk"
)

func run(productEndpoint, personalAccessToken, workspaceName string) error {
 ctx := context.Background()
 client, err := sdk.NewWithPersonalAccessToken(productEndpoint, personalAccessToken, sdk.WithTimeout(30*time.Second))
 if err != nil {
 return err
 }
 workspace, err := client.EnsureWorkspace(ctx, workspaceName)
 if err != nil {
 return err
 }
 _, err = workspace.DBConnection(ctx)
 return err
}
`

Example task index:

Use this index before copying from the reference catalog. It keeps each copied
snippet anchored to one user task, identifies caller-owned variables, and shows
the handle/result that proves the task can continue.
After choosing an anchor, follow the selected Flow Recipe in recipe order; do not
treat the anchor as a complete workflow by itself. Check before run entries summarize task-specific Error Recovery, Permission and Scope, Confirmation and Preview, and Progress Visibility Coverage.

| User task | Copy anchor | Replace | Result | Continue with | Check before run |
|-----------|-------------|---------|--------|---------------|------------------|
| Bootstrap a UI workspace and inspect identity | `client.EnsureWorkspace(ctx` | `productEndpoint`, `apiKey`, `workspaceName`. | `workspace` result. | `WorkspaceHandle` descendants from the selected Flow Recipe. | Check auth error handling, workspace permission scope, duplicate-name confirmation, and progress visibility. |
| Manage workspace members | `workspace.InviteMember(ctx` | `userDisplayName`, explicit `defaultRoleID`, `userEmail` or `userMobileNumber`, canonical `assignedRoleIDs` containing that Default Role, a member ID for lifecycle operations, and `iam_user_id` from member detail for role bindings. | `invitation` result, then accepted member detail with `iam_user_id`. | Bind `WorkspaceMemberHandle` with the member ID for lifecycle calls; pass `iam_user_id` to IAM role-binding calls. | Check IAM error handling, role-assignment scope, confirmation, and audit/progress visibility. |
| Browse catalog resources and operate tables | `workspace.PrepareCatalog(ctx` | `catalogName`, `databaseName`, `tableName`, `tableColumns`, `tableDataURL`, `tablePageSize`. | `catalog`, `database`, `table`, and `rows` results. | `DatabaseHandle` or `TableHandle` from the selected Flow Recipe. | Check catalog error handling, workspace permission scope, destructive table confirmation, and page/progress visibility. |
| Manage volumes, folders, and files | `database.PrepareVolume(ctx` | `volumeName`, `fileName`, `csvBytes`, `downloadAsZip`. | `volume`, `file`, and `download` results. | `VolumeHandle`, `FolderHandle`, or `FileHandle` from the selected Flow Recipe. | Check file error handling, workspace permission scope, delete/clean confirmation, and upload/download progress visibility. |
| Deploy, run, inspect, rerun, and cancel workflows | `workspace.DeployWorkflow(ctx` | `workflowName`, `workflowID`, `dslYAML`, `workflowRunInput`, `executionID`, `nodeExecutionID`, `workflowRerunMode`. | `workflow`, `runData`, `run`, and `createdRerun` results. | `WorkflowHandle`, `WorkflowRunHandle`, or `WorkflowRunNodeHandle` from the selected Flow Recipe. | Check workflow error handling, workspace permission scope, rerun/cancel confirmation, and run progress visibility. |
| Design workflow custom operators and templates | `workspace.CreateCustomOperatorFromSpec(ctx` | `operatorName`, `operatorTestInput`, `workflowTemplateName`, `dslYAML`. | `operator`, `testedOperator`, and `template` results. | `CustomOperatorHandle` or `WorkflowTemplateHandle` from the selected Flow Recipe. | Check validation error handling, workspace permission scope, enable/delete confirmation, and test progress visibility. |
| Publish and invoke WorkItem API services | `service.Publish(ctx` | `nodeID`, `serviceVersion`, `computeResourceID`, `serviceName`, `serviceType`, `servicePayload`, `serviceTimeoutSeconds`, `serviceMaxConcurrency`, `serviceRateLimitPerMin`. | `service`, `publishedService`, and `invokedService` results. | `WorkitemAPIServiceHandle` from the selected Flow Recipe. | Check publish/invoke error handling, service permission scope, enable/disable confirmation, and invocation progress visibility. |
| Review lineage artifacts and rerun from nodes/blocks | `file.LineageOverview(ctx` | `artifactID`. | `fileLineage`, `artifact`, and `artifactBlocks` results. | `ArtifactHandle`, `ArtifactBlockHandle`, or `ArtifactNodeHandle` from the selected Flow Recipe. | Check lineage error handling, artifact permission scope, rerun/revision confirmation, and rerun progress visibility. |
| Ask Explore questions with selected sources | `session.QueryWithSources(ctx` | `exploreQuestion`, `catalogID`, `semanticModelID`, `exploreDatabaseName`, `exploreTableName`. | `sources`, `session`, and `answer` results. | `ExploreSessionHandle` or `ExploreMessageHandle` from the selected Flow Recipe. | Check query error handling, source permission scope, stream/feedback confirmation, and answer progress visibility. |
| Browse Explore source tables and columns | `workspace.ExploreData()` | `databaseID`, `tableID`, `exploreDatabaseName`, `exploreTableName`, `tablePageSize`. | `exploreData`, `exploreDatabase`, `exploreTable`, and `columns` results. | `ExploreDataHandle`, `ExploreDatabaseHandle`, or `ExploreTableHandle` from the selected Flow Recipe. | Check browse error handling, source permission scope, broad-scan confirmation, and page progress visibility. |
| Manage semantic models and entries | `workspace.CreateSemanticModel(ctx` | `semanticModelName`, `semanticEntryKind`, `semanticEntryKey`, `semanticEntrySpec`, `tableName`, `tableID`. | `semanticModel`, `semanticEntry`, and `validatedModel` results. | `SemanticModelHandle` or `SemanticEntryHandle` from the selected Flow Recipe. | Check semantic error handling, model permission scope, import/delete confirmation, and validation progress visibility. |
| Manage connectors plus import/export tasks | `connector.CreateFileImportTask(ctx` | `connectorName`, `importTaskURIs`, `configType`, `importTaskName`, `importTaskUpdatedName`, `volumeID`, `fileID`, `loadModeConfig`, `fileFilterConfig`, `updatedImportTaskURIs`, `exportTaskName`, `exportType`, `s3Config`, `exportFilePath`. | `connector`, `importTask`, and `exportTask` results. | `ConnectorHandle`, `ImportTaskHandle`, or `ExportTaskHandle` from the selected Flow Recipe. | Check connector error handling, external permission scope, import/export confirmation, and transfer progress visibility. |
| Use product agents through A2A | `agent.SendText(ctx` | `agentCode`, `agentPrompt`, `requestID`, `statusRequestID`, `agentMessageID`. | `agent`, `agentTask`, `agentTaskID`, and `agentTaskStatus` results. | `AgentHandle` and A2A task calls from the selected Flow Recipe. | Check A2A error handling, agent permission scope, cancel/input confirmation, and stream/task progress visibility. |
| Configure model providers and routers | `llm.CreateBackend(ctx` | `providerBackendName`, `providerModelNames`, `modelEndpoint`, `routerStrategy`. | `llm`, `llmBackend`, and `router` results. | `ModelProviderHandle`, `ProviderBackendHandle`, or `ProviderRouterHandle` from the selected Flow Recipe. | Check provider error handling, secret permission scope, router/delete confirmation, and probe progress visibility. |
| Manage compute resources | `workspace.CreateComputeResource(ctx` | `specID`, `workerImage`, `computeCPU`, `computeMemoryGB`, `computeMinReplicas`, `computeMaxReplicas`. | `compute` and `suspended` results. | `ComputeResourceHandle` from the selected Flow Recipe. | Check compute error handling, resource permission scope, action/delete confirmation, and action progress visibility. |
| Publish and subscribe data shares | `workspace.CreateDataSharePublish(ctx` | `publishName`, `sourceDatabaseID`, `tableScope`, `sourceTableIDs`, `targetWorkspaceID`, `subscriptionID`, `subscriptionName`, `dataShareRemark`. | `publish`, `subscription`, and `subscribed` results. | `DataSharePublishHandle` or `DataShareSubscriptionHandle` from the selected Flow Recipe. | Check share error handling, cross-workspace permission scope, subscribe/delete confirmation, and share progress visibility. |
| Work in the SQL editor and query history | `workspace.ExecuteSQL(ctx` | `sqlText`, `sqlWorkbookName`, `statementID`, `targetDatabaseName`, `sqlResultLimit`. | `sqlMetadata`, `workbook`, `query`, and `statement` results. | `SQLMetadataHandle`, `SQLWorkbookHandle`, `SQLQueryHandle`, or `SQLStatementHandle` from the selected Flow Recipe. | Check SQL error handling, database permission scope, cancel/drop confirmation, and query progress visibility. |

Example selection rule: the representative Go snippets below are a reference
catalog, not one complete runnable workflow. For a user request, first choose
the Cross-Domain User Journey or User Story Matrix task, then copy only the
minimal ordered lines required by that task's User Story Flow Recipe. Do not
combine unrelated lines from the catalog into one generated workflow.

`go
ctx := context.Background()
client, err := sdk.New(productEndpoint, sdk.WithAPIKey(apiKey), sdk.WithTimeout(timeout))
workspace, err := client.EnsureWorkspace(ctx, workspaceName)
profile, err := workspace.DBConnection(ctx)
db, err := workspace.DBConnection(ctx)
invitation, err := workspace.InviteMember(ctx, userDisplayName, roleID, sdk.WithUserEmail(userEmail), sdk.WithUserRoleIDs(roleID))
user, err := workspace.Member(activeMemberUserID)
member, err := user.Info(ctx)
canonicalIAMUserID := member.GetIamUserId()
bindings, err := workspace.IAM().UserRoleBindings(ctx, canonicalIAMUserID)
expectedBindingVersion, err := sdk.IAMBindingVersionNumber(bindings)
updatedBindings, err := workspace.IAM().PutUserRoleBindings(ctx, canonicalIAMUserID, &sdk.IAMUserRoleBindingsRequest{
	AssignedRoleIds: assignedRoleIDs, DefaultRoleId: defaultRoleID,
	ExpectedBindingVersion: expectedBindingVersion, ExpectedDefaultRoleVersion: bindings.GetDefaultRoleVersion(),
	RequestId: requestID,
})
catalog, err := workspace.PrepareCatalog(ctx, catalogName)
database, err := catalog.PrepareDatabase(ctx, databaseName)
catalogs, catalogList, err := workspace.Catalogs(ctx)
databases, databaseList, err := catalog.Databases(ctx)
children, err := database.Children(ctx)
volumes, volumeChildren, err := database.Volumes(ctx)
tables, tableChildren, err := database.Tables(ctx)
table, createdTable, err := database.CreateTable(ctx, tableName, tableColumns, sdk.WithTableDataFileURL(tableDataURL))
rows, err := table.Data(ctx, sdk.WithTableDataPageSize(tablePageSize))
previewRows, err := table.Preview(ctx, sdk.WithTablePreviewLines(tablePreviewLines))
volume, err := database.PrepareVolume(ctx, volumeName)
file, err := volume.UploadBytesHandle(ctx, fileName, csvBytes)
download, err := file.Download(ctx, sdk.WithFileAsZip(downloadAsZip))
defer download.Body.Close()
// First deployment: let the server allocate the ID. Pass an existing ID to publish a new version.
workflow, deployed, err := workspace.DeployWorkflow(ctx, workflowName, dslYAML, "")
workflowID := workflow.ID()
runData, err := workflow.Run(ctx, sdk.WithWorkflowRunInput(workflowRunInput))
run, err := workflow.RunHandle(executionID)
runNode, err := run.NodeHandle(nodeKey)
rerunPlan, err := runNode.RerunPlan(ctx, sdk.WithQueryParam("source_node_execution_id", nodeExecutionID))
createdRerun, err := runNode.CreateRerun(ctx, workflowRerunMode, nodeExecutionID, sdk.WithExpectedWorkflowRerunContractHash(rerunPlan.GetPlan().GetRerunContractHash()))
operatorSpec := sdk.CustomOperatorSpec{Name: operatorName, Identifier: operatorIdentifier, Description: operatorDescription, InputSchema: inputSchema, OutputSchema: outputSchema}
operator, createdOperator, err := workspace.CreateCustomOperatorFromSpec(ctx, operatorSpec)
testedOperator, err := operator.TestWithInput(ctx, sdk.CustomOperatorTestInput{Input: operatorTestInput})
template, createdTemplate, err := workspace.CreateWorkflowTemplate(ctx, workflowTemplateName, dslYAML)
service, err := workspace.WorkitemAPIService(nodeID, serviceVersion)
publishedService, err := service.Publish(ctx, sdk.WorkitemAPIServicePublishSpec{Version: serviceVersion, ComputeResourceID: computeResourceID, TimeoutSeconds: serviceTimeoutSeconds, MaxConcurrency: serviceMaxConcurrency, RateLimitPerMin: serviceRateLimitPerMin})
invokedService, err := service.Invoke(ctx, sdk.WorkitemAPIServiceInvokeSpec{ServiceName: serviceName, Type: serviceType, Version: serviceVersion, Payload: servicePayload})
fileLineage, err := file.LineageOverview(ctx)
artifact, err := workspace.Artifact(artifactID)
artifactBlocks, err := artifact.OutputBlocks(ctx)
artifactNode, err := artifact.Node(nodeID)
nodeRerun, err := artifactNode.Rerun(ctx, sdk.WithLineageRerunMode(lineageRerunMode))
sources := sdk.NewExploreDataSources().WithTable(exploreDatabaseName, []string{exploreTableName}, catalogID).WithSemanticModels(semanticModelID)
session, created, err := workspace.CreateExploreSession(ctx, exploreSessionTitle)
answer, err := session.QueryWithSources(ctx, exploreQuestion, sources)
exploreData := workspace.ExploreData()
overview, err := exploreData.Overview(ctx)
exploreDatabase, err := exploreData.Database(databaseID, exploreDatabaseName)
exploreTables, err := exploreDatabase.Tables(ctx)
exploreTable, err := exploreDatabase.Table(tableID, exploreTableName)
columns, err := exploreTable.Columns(ctx)
semanticModel, createdModel, err := workspace.CreateSemanticModel(ctx, semanticModelName, sdk.WithSemanticModelTables([]string{tableName}))
semanticEntry, createdEntry, err := semanticModel.CreateEntry(ctx, sdk.SemanticEntryInput{Kind: semanticEntryKind, Key: semanticEntryKey, Spec: semanticEntrySpec, Tables: []string{tableName}})
validatedModel, err := semanticModel.Validate(ctx)
connector, createdConnector, err := workspace.CreateConnector(ctx, connectorName, sourceType, usageType)
importTask, imported, err := connector.CreateFileImportTask(ctx, sdk.FileImportTaskSpec{ConfigType: configType, Name: importTaskName, VolumeID: volumeID, URIs: importTaskURIs, LoadModeConfig: loadModeConfig, FileFilterConfig: fileFilterConfig})
err = importTask.UpdateConfig(ctx, sdk.ImportTaskUpdateSpec{LoadModeConfig: loadModeConfig, Name: importTaskUpdatedName, FileFilterConfig: fileFilterConfig, URIs: updatedImportTaskURIs})
exportTask, exported, err := connector.CreateExportTaskFromSpec(ctx, sdk.ExportTaskSpec{Name: exportTaskName, ConnectorName: connectorName, Type: exportType, Config: sdk.ExportTaskConfig{S3Config: s3Config}, Files: []sdk.ExportTaskFile{{FileID: fileID, FullPath: exportFilePath}}})
exportState, err := exportTask.State(ctx)
agent, err := workspace.AgentByCode(agentCode)
agentTask, err := agent.SendText(ctx, sdk.AgentTextMessage{RequestID: requestID, MessageID: agentMessageID, Text: agentPrompt})
agentTaskID, err := sdk.AgentA2ATaskID(agentTask)
agentTaskStatus, err := agent.GetTask(ctx, sdk.AgentTaskRequest{TaskID: agentTaskID, RequestID: statusRequestID})
llm := workspace.LLMProvider()
llmBackend, createdLLM, err := llm.CreateBackend(ctx, providerBackendName, sdk.WithProviderBackendAddress(modelEndpoint), sdk.WithProviderBackendModels(providerModelNames...))
router, err := llm.Router().Update(ctx, sdk.WithRouterStrategy(routerStrategy))
group, err := workspace.AlertGroup(alertGroupID)
err = workspace.CreateAlertReceiver(ctx, group.ID(), receiverName, notifyType, receiverStatus, sdk.WithReceiverEmail(receiverEmail))
receiver, err := workspace.AlertReceiver(receiverID)
err = workspace.CreateAlertRule(ctx, expressionID, alertLevel, alertCategory, sdk.WithAlertRuleReceivers(receiver.ID()))
rule, err := workspace.AlertRule(alertRuleID)
history, err := group.History(ctx, sdk.WithAlertingPage(alertingPage), sdk.WithAlertingSize(alertingSize))
compute, createdCompute, err := workspace.CreateComputeResource(ctx, workerImage, specID, computeCPU, computeMemoryGB, sdk.WithComputeMinReplicas(computeMinReplicas), sdk.WithComputeMaxReplicas(computeMaxReplicas))
suspended, err := compute.Suspend(ctx)
tableScope := &sdk.DataShareScope{Mode: "selected", ObjectIds: sourceTableIDs}
publish, createdPublish, err := workspace.CreateDataSharePublish(ctx, publishName, sourceDatabaseID, tableScope, []string{targetWorkspaceID}, sdk.WithDataShareRemark(dataShareRemark))
subscription, err := workspace.DataShareSubscription(subscriptionID)
subscribed, err := subscription.Subscribe(ctx, subscriptionName)
sqlMetadata := workspace.SQLMetadata()
sqlDatabases, err := sqlMetadata.Databases(ctx)
sqlDatabase, err := sqlMetadata.Database(targetDatabaseName)
sqlTables, err := sqlDatabase.Tables(ctx)
workbook, createdWorkbook, err := workspace.CreateSQLWorkbook(ctx, sqlWorkbookName)
query, startedQuery, err := workspace.ExecuteSQL(ctx, sqlText, sdk.WithSQLQueryDBName(targetDatabaseName))
statement, err := workspace.SQLStatement(statementID)
resultRows, err := statement.Result(ctx, sdk.WithSQLResultLimit(sqlResultLimit))
`

## SQL result download API contract after PR #14017

The Go Product SDK does not currently expose a helper for SQL result downloads.
Consumers that call the backend directly must use:

```text
POST /newmoi/query/result/download
{"statement_id":"<owned saved-result statement ID>"}
```

Use the normal Product API authentication and workspace context. Get
`statementID` from SQL execution or query history. A missing ID is rejected, and
the server does not re-execute SQL text or accept `query` / `db_name` as a
compatibility fallback.

The route returns a streamed CSV response. The calling Go HTTP client owns
`response.Body` and must consume and close it. This repository change does not
add a Go SDK method, modify SDK version metadata, or publish a package.

## Release train validation

Documentation-only change for the v0.1.1 sandbox release.
