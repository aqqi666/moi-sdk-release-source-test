# MOI Product Python SDK

Python SDK for UI-visible MOI product APIs.

The existing `MemoryService` / `ConsumerMemoryHandle` target the legacy Consumer Memory/Profile API. Current MOI does not expose those routes; these entries are not a current capability. See [Legacy API availability](../docs/product-sdk-capabilities.md#legacy-api-availability).

Typed product result objects are generated from `../proto/product/*.proto`.

Runner and sandbox services are available through `client.runners(workspace_id)`
and `client.sandboxes(workspace_id)`. `SandboxEgressEndpoint`, `SandboxQuotaStatus`
and `SandboxQuota` are exported from `moi_product_sdk` alongside the existing
request/result types. Quota request fields preserve explicit zero versus omission.
See [Runner and sandbox HTTP alignment](../docs/product-sdk-capabilities.md#runner-and-sandbox-http-alignment).

`Error.details` preserves nested dictionaries, lists and scalar JSON values,
including exact integer IDs. Owner code/message, HTTP status, transport request
ID and repair data remain available. See [Structured error details](../docs/product-sdk-capabilities.md#structured-error-details).

File imports may omit `name` and `volume_id`; MOI supplies an absent name. `ImportTaskCreateSpec` and `FileImportTaskSpec` accept an optional `task_id`, which is sent unchanged. `ImportTaskUpdateSpec` edits the name, load mode, file filter and URIs; choose the target volume at creation. Export tasks require a name and accept the optional `creator` label.

`KnowledgeService.create_with_sources` accepts `with_semantic_model_with_sources_target_catalog_id` to choose the destination Catalog and `with_semantic_model_with_sources_source_selections` to select existing Catalog files or tables. The CLI exposes `--target-catalog-id` and `--source-selections-file`; use `moi-cli schema semantic-model create-with-sources --argument source-selections-file` for the file structure.

`KnowledgeService.append_sources(..., selections=...)` also accepts Catalog selections; the CLI exposes `semantic-model append-sources --source-selections-file`. Knowledge creation exposes descriptions and the image-index setting, while `semantic-model update` accepts `--description`, `--tables-file` and `--files-file` to pass the corresponding SDK options.

Catalog tree navigation supports pagination, search, resource types and exact resource IDs. `CatalogService.tree(include_table_leaves=False)` excludes table leaves while omission keeps the server default. An empty `resource_types` list omits the filter, matching Go's wire encoding. The CLI exposes navigation through `catalog tree`, `system-tree` and `database-table-leaves`; `catalog search-data-dashboard-tables` exposes permission-scoped table search across databases.

Compute creation and updates accept `with_compute_kind` / `with_compute_update_kind` and `with_compute_py_requirements_txt` / `with_compute_update_py_requirements_txt`. Both spec operations accept `with_compute_spec_node_placement`. See [Compute configuration](../docs/product-sdk-capabilities.md#compute-configuration) for CLI flags, clearing behavior and dependency observations.

Knowledge creation accepts `knowledge.create_with_spec` with `SemanticModelCreateSpec` for embedding preservation and drawing settings. Keep description, tables and files in the existing options. See [Knowledge creation controls](../docs/product-sdk-capabilities.md#knowledge-creation-controls) for omission, explicit false and CLI usage.

Workflow template creation and updates expose key, description, input-form and builtin options in the CLI. MOWL templates have a dedicated update method and handle operation. Template response IDs use the handler’s 64-bit range. See [Workflow template controls](../docs/product-sdk-capabilities.md#workflow-template-controls).

## Current IAM capabilities

The existing IAM service accepts optional capability IDs:

```python
capabilities = workspace.iam().current_principal_capabilities("action.role.create", "navigation.roles")
```

Omit IDs to retrieve the full projection. The server evaluates only supported requested IDs and returns the existing metadata, denial reasons and resource scopes in capability ID order. Unknown IDs, including empty values, are reported in `capabilities.unsupported_capability_ids` with HTTP 200. If all IDs are unsupported, `items` is empty; duplicate IDs are returned once. The SDK sends IDs unchanged. See the [API contract](../../docs/iam/07-public-api-frontend-sdk-contracts.md#21-按-id-查询当前主体-capability).

## A2A message/send semantics

The server answers `message/send` at task admission (A2A 0.3 non-blocking default): a still-running task returns its persisted non-terminal projection (`kind=task`, `status.state` of `submitted` or `working`, with `metadata.eventCursor`), while a task settled inside the admission window keeps its terminal or acknowledgement answer unchanged. `configuration.blocking: true` is explicitly rejected with HTTP 400, JSON-RPC `-32602`, and `error.data.reason = BLOCKING_UNSUPPORTED`; other `configuration` keys are ignored.

`AgentService.a2a()` and `AgentHandle.send_text()` keep their signatures: when a send result is a non-terminal task, the SDK internally follows it to a terminal state before returning — first through `tasks/resubscribe` resuming at the persisted `eventCursor` (bounded reconnects with backoff), degrading to `tasks/get` polling every 2 seconds when the stream cannot be held. Message-kind results (feedback ack, run-control ack, provider interaction) and already-terminal tasks pass through unchanged. The terminal set is `completed`/`failed`/`canceled`/`rejected` plus the interrupted `input-required`/`auth-required` states, which are handed back to the caller for handling.

For explicit protocol control that returns the admission result immediately, pass `no_wait=True` on `A2ARequest` to `agent.a2a(...)` or `AgentService.a2a(...)`. This matches Go's `A2ARequest.NoWait` and `moi-cli agent a2a --no-wait`. It only skips the client's task follow; the flag is never sent to the server. Keep the returned task ID to query, resume or cancel the task later.

`with_a2a_wait_timeout(seconds)` bounds the whole follow (default 600) and is independent of the per-request `with_timeout`. When the budget is exhausted the call raises `Error("ErrTimeout", ...)` whose `details` carry `task_id`, so the caller can resume the persisted task explicitly instead of treating it as lost.

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
40. Bootstrap through the product endpoint, then use `ensure_workspace` for name-based find/create or `workspace` only for an already sourced workspace id before continuing with `WorkspaceHandle` for workspace-scoped tasks.
41. Prefer the listed handle/spec entry points whenever they exist; do not start from `client.<domain>(workspace_id)` for a promoted user task.
42. Use route-aligned services only as an explicit escape hatch for domains without a promoted user-story facade or when route-level control is required.
43. Do not expose the Apps backend domain through the Python Product SDK, including `/apps`, `/apps/:app_code`, or app-specific workflows.
44. When a handle requires an existing id, obtain that id from a typed SDK create/list/get result, a UI-selected resource, or explicit user input; handle constructors only bind existing resources and do not create or discover them; do not invent ids or infer them from `ProductData`.
47. Treat error-only write methods as success/failure checks only; they do not return product data, ids, or handles and must not be used as the source for the next SDK call.

Task quick start:

Use the [Cross-Domain User Journeys](../docs/product-sdk-capabilities.md#cross-domain-user-journeys) first when the request spans multiple product areas. Then use the [AI Task Selection Guide](../docs/product-sdk-capabilities.md#ai-task-selection-guide) for intent signals and avoid rules before applying this table. Use the [AI Intent Disambiguation Matrix](../docs/product-sdk-capabilities.md#ai-intent-disambiguation-matrix) when wording could match multiple tasks or a route-aligned escape hatch. Use the [User Context Entry Matrix](../docs/product-sdk-capabilities.md#user-context-entry-matrix) to choose the SDK starting object from the context already available. Check the [User Story Ergonomic Usage Tiers](../docs/product-sdk-capabilities.md#user-story-ergonomic-usage-tiers) so examples start with the minimal path and add advanced control only when needed. Check the [User Story Operation Intent Coverage](../docs/product-sdk-capabilities.md#user-story-operation-intent-coverage) before adding lifecycle actions such as create/configure, update/action, delete/cancel, or observe/result. Check the [User Story Capability Availability Coverage](../docs/product-sdk-capabilities.md#user-story-capability-availability-coverage) before choosing method names. Check the [User Story Abstraction Fitness](../docs/product-sdk-capabilities.md#user-story-abstraction-fitness) before picking handles or specs so the code follows the user mental model instead of route-group translation. After choosing a row, follow its [User Story Flow Recipe](../docs/product-sdk-capabilities.md#user-story-flow-recipes) before writing code. Check the [User Story State Handoff Coverage](../docs/product-sdk-capabilities.md#user-story-state-handoff-coverage) before passing values between SDK calls. Check the [Cross-Domain Journey Risk Coverage](../docs/product-sdk-capabilities.md#cross-domain-journey-risk-coverage) before composing retries, cancellations, reruns, permission-sensitive operations, or external dependency calls. Check the [User Story Discovery and Selection Coverage](../docs/product-sdk-capabilities.md#user-story-discovery-and-selection-coverage) before constructing handles from ids. Check the [User Story Selection Disambiguation Coverage](../docs/product-sdk-capabilities.md#user-story-selection-disambiguation-coverage) before selecting one resource from list, search, name, or paginated results. Then check the [User Story Outcome Contract](../docs/product-sdk-capabilities.md#user-story-outcome-contracts) so generated code stops at a user-visible result and keeps caller-owned inputs explicit.

| User task | Prefer |
|-----------|--------|
| Bootstrap a UI workspace and inspect identity | `Client.ensure_workspace`, `Client.workspace`, `WorkspaceHandle` |
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

- Product Python SDK clients use the same product API gateway and RBAC layer used by the MOI UI.
- Local SDK development and integration tests may use `moi-backend` directly when no product gateway is running.
- `moi-backend` must support user-scoped API key authentication for SDK calls, not only UI token/session authentication.
- Product Python SDK clients must not use `moi-core/catalog` as their default endpoint.
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

Minimal Python bootstrap:

`product_endpoint` must include the environment's product API base path, for
example `https://example.com/newmoi` or another environment-specific prefix.
The SDK appends product-relative paths to that address and does not add
`/newmoi` itself.

`python
import moi_product_sdk as sdk


def run(product_endpoint: str, api_key: str, workspace_name: str):
 client = sdk.Client(product_endpoint, sdk.with_api_key(api_key))
 workspace = client.ensure_workspace(workspace_name)
 return workspace.db_connection()
`

Example task index:

Use this index before copying from the reference catalog. It keeps each copied
snippet anchored to one user task, identifies caller-owned variables, and shows
the handle/result that proves the task can continue.
After choosing an anchor, follow the selected Flow Recipe in recipe order; do not
treat the anchor as a complete workflow by itself. Check before run entries summarize task-specific Error Recovery, Permission and Scope, Confirmation and Preview, and Progress Visibility Coverage.

| User task | Copy anchor | Replace | Result | Continue with | Check before run |
|-----------|-------------|---------|--------|---------------|------------------|
| Bootstrap a UI workspace and inspect identity | `client.ensure_workspace(` | `product_endpoint`, `api_key`, `workspace_name`. | `workspace` result. | `WorkspaceHandle` descendants from the selected Flow Recipe. | Check auth error handling, workspace permission scope, duplicate-name confirmation, and progress visibility. |
| Manage workspace members | `workspace.invite_member(` | `user_display_name`, explicit `default_role_id`, `user_email` or `user_mobile_number`, canonical `assigned_role_ids` containing that Default Role, a member ID for lifecycle operations, and `iam_user_id` from member detail for role bindings. | `invitation` result, then accepted member detail with `iam_user_id`. | Bind `WorkspaceMemberHandle` with the member ID for lifecycle calls; pass `iam_user_id` to IAM role-binding calls. | Check IAM error handling, role-assignment scope, confirmation, and audit/progress visibility. |
| Browse catalog resources and operate tables | `workspace.prepare_catalog(` | `catalog_name`, `database_name`, `table_name`, `table_columns`, `table_data_url`, `table_page_size`. | `catalog`, `database`, `table`, and `rows` results. | `DatabaseHandle` or `TableHandle` from the selected Flow Recipe. | Check catalog error handling, workspace permission scope, destructive table confirmation, and page/progress visibility. |
| Manage volumes, folders, and files | `database.prepare_volume(` | `volume_name`, `folder_name`, `file_name`, `local_file_path`, `csv_bytes`, `download_as_zip`. | `volume`, `file`, and `download` results. | `VolumeHandle`, `FolderHandle`, or `FileHandle` from the selected Flow Recipe. | Check file error handling, workspace permission scope, delete/clean confirmation, and upload/download progress visibility. |
| Deploy, run, inspect, rerun, and cancel workflows | `workspace.deploy_workflow(` | `workflow_name`, `workflow_id`, `dsl_yaml`, `workflow_run_input`, `execution_id`, `node_id`, `node_execution_id`, `workflow_rerun_mode`. | `workflow`, `run_data`, `run`, and `created_rerun` results. | `WorkflowHandle`, `WorkflowRunHandle`, or `WorkflowRunNodeHandle` from the selected Flow Recipe. | Check workflow error handling, workspace permission scope, rerun/cancel confirmation, and run progress visibility. |
| Design workflow custom operators and templates | `workspace.create_custom_operator_from_spec(` | `operator_name`, `operator_test_input`, `workflow_template_name`, `dsl_yaml`. | `operator`, `tested_operator`, and `workflow_template` results. | `CustomOperatorHandle` or `WorkflowTemplateHandle` from the selected Flow Recipe. | Check validation error handling, workspace permission scope, enable/delete confirmation, and test progress visibility. |
| Publish and invoke WorkItem API services | `service.publish(` | `node_id`, `service_version`, `compute_resource_id`, `service_name`, `service_type`, `service_payload`, `service_timeout_seconds`, `service_max_concurrency`, `service_rate_limit_per_min`. | `service`, `published_service`, and `invoked_service` results. | `WorkitemAPIServiceHandle` from the selected Flow Recipe. | Check publish/invoke error handling, service permission scope, enable/disable confirmation, and invocation progress visibility. |
| Review lineage artifacts and rerun from nodes/blocks | `file.lineage_overview()` | `artifact_id`. | `file_lineage`, `artifact`, and `artifact_blocks` results. | `ArtifactHandle`, `ArtifactBlockHandle`, or `ArtifactNodeHandle` from the selected Flow Recipe. | Check lineage error handling, artifact permission scope, rerun/revision confirmation, and rerun progress visibility. |
| Ask Explore questions with selected sources | `session.query_with_sources(` | `explore_question`, `catalog_id`, `database_id`, `table_id`, `semantic_model_id`, `explore_database_name`, `explore_table_name`. | `sources`, `session`, and `answer` results. | `ExploreSessionHandle` or `ExploreMessageHandle` from the selected Flow Recipe. | Check query error handling, source permission scope, stream/feedback confirmation, and answer progress visibility. |
| Browse Explore source tables and columns | `workspace.explore_data()` | `database_id`, `table_id`, `explore_database_name`, `explore_table_name`, `table_page_size`. | `explore_data`, `explore_database`, `explore_table`, and `columns` results. | `ExploreDataHandle`, `ExploreDatabaseHandle`, or `ExploreTableHandle` from the selected Flow Recipe. | Check browse error handling, source permission scope, broad-scan confirmation, and page progress visibility. |
| Manage semantic models and entries | `workspace.create_semantic_model(` | `semantic_model_name`, `semantic_entry_kind`, `semantic_entry_key`, `semantic_entry_spec`, `table_name`. | `semantic_model`, `semantic_entry`, and `validated_model` results. | `SemanticModelHandle` or `SemanticEntryHandle` from the selected Flow Recipe. | Check semantic error handling, model permission scope, import/delete confirmation, and validation progress visibility. |
| Manage connectors plus import/export tasks | `connector.create_file_import_task(` | `connector_name`, `import_task_uris`, `config_type`, `import_task_name`, `import_task_updated_name`, `volume_id`, `file_id`, `load_mode_config`, `file_filter_config`, `updated_import_task_uris`, `export_task_name`, `export_type`, `s3_config`, `export_file_path`. | `connector`, `import_task`, and `export_task` results. | `ConnectorHandle`, `ImportTaskHandle`, or `ExportTaskHandle` from the selected Flow Recipe. | Check connector error handling, external permission scope, import/export confirmation, and transfer progress visibility. |
| Use product agents through A2A | `agent.send_text(` | `agent_code`, `agent_prompt`, `request_id`, `status_request_id`, `agent_message_id`. | `agent`, `agent_task`, `agent_task_id`, and `agent_task_status` results. | `AgentHandle` and A2A task calls from the selected Flow Recipe. | Check A2A error handling, agent permission scope, cancel/input confirmation, and stream/task progress visibility. |
| Configure model providers and routers | `llm.create_backend(` | `provider_backend_name`, `provider_model_names`, `model_endpoint`, `router_strategy`, `embedding_model_names`. | `llm`, `llm_backend`, and `router` results. | `ModelProviderHandle`, `ProviderBackendHandle`, or `ProviderRouterHandle` from the selected Flow Recipe. | Check provider error handling, secret permission scope, router/delete confirmation, and probe progress visibility. |
| Manage compute resources | `workspace.create_compute_resource(` | `spec_id`, `worker_image`, `compute_cpu`, `compute_memory_gb`, `compute_min_replicas`, `compute_max_replicas`. | `compute` and `suspended` results. | `ComputeResourceHandle` from the selected Flow Recipe. | Check compute error handling, resource permission scope, action/delete confirmation, and action progress visibility. |
| Publish and subscribe data shares | `workspace.create_data_share_publish(` | `publish_name`, `source_database_id`, `table_scope`, `source_table_ids`, `target_workspace_id`, `subscription_id`, `subscription_name`, `data_share_remark`. | `publish`, `subscription`, and `subscribed` results. | `DataSharePublishHandle` or `DataShareSubscriptionHandle` from the selected Flow Recipe. | Check share error handling, cross-workspace permission scope, subscribe/delete confirmation, and share progress visibility. |
| Work in the SQL editor and query history | `workspace.execute_sql(` | `sql_text`, `sql_workbook_name`, `statement_id`, `target_database_name`, `sql_result_limit`. | `sql_metadata`, `workbook`, `query`, `statement`, and `rows` results. | `SQLMetadataHandle`, `SQLWorkbookHandle`, `SQLQueryHandle`, or `SQLStatementHandle` from the selected Flow Recipe. | Check SQL error handling, database permission scope, cancel/drop confirmation, and query progress visibility. |

Example selection rule: the representative Python snippets below are a reference
catalog, not one complete runnable workflow. For a user request, first choose
the Cross-Domain User Journey or User Story Matrix task, then copy only the
minimal ordered lines required by that task's User Story Flow Recipe. Do not
combine unrelated lines from the catalog into one generated workflow.

`python
import moi_product_sdk as sdk

client = sdk.Client(product_endpoint, sdk.with_api_key(api_key))
workspace = client.ensure_workspace(workspace_name)
profile = workspace.db_connection()
db = workspace.db_connection()
invitation = workspace.invite_member(user_display_name, role_id, sdk.with_user_email(user_email), sdk.with_user_role_ids(role_id))
user = workspace.member(active_member_user_id)
member = user.info()
canonical_iam_user_id = member.iam_user_id
bindings = workspace.iam().user_role_bindings(canonical_iam_user_id)
expected_binding_version = sdk.iam_binding_version_number(bindings)
updated_bindings = workspace.iam().put_user_role_bindings(
    canonical_iam_user_id,
    sdk.IAMUserRoleBindingsRequest(
        assigned_role_ids=assigned_role_ids,
        default_role_id=default_role_id,
        expected_binding_version=expected_binding_version,
        expected_default_role_version=bindings.default_role_version,
        request_id=request_id,
    ),
)
catalog = workspace.prepare_catalog(catalog_name)
database = catalog.prepare_database(database_name)
catalogs, catalog_list = workspace.catalogs()
databases, database_list = catalog.databases()
children = database.children()
volumes, volume_children = database.volumes()
tables, table_children = database.tables()
table, created_table = database.create_table_from_columns(table_name, table_columns, sdk.with_table_data_file_url(table_data_url))
rows = table.data(sdk.with_table_data_page_size(table_page_size))
preview_rows = table.preview(sdk.with_table_preview_lines(table_preview_lines))
volume = database.prepare_volume(volume_name)
volume = workspace.prepare_data_volume(catalog_name, database_name, volume_name)
uploaded = volume.upload_bytes(file_name, csv_bytes)
file = volume.upload_bytes_handle(file_name, csv_bytes)
local_file = volume.upload_file_handle(local_file_path)
volume_preview = volume.upload_bytes_preview(file_name, csv_bytes)
local_volume_preview = volume.upload_file_preview(local_file_path)
file = workspace.upload_bytes_to_data_volume(catalog_name, database_name, volume_name, file_name, csv_bytes)
local_file = workspace.upload_file_to_data_volume(catalog_name, database_name, volume_name, local_file_path)
previewed = workspace.upload_bytes_preview_to_data_volume(catalog_name, database_name, volume_name, file_name, csv_bytes)
local_previewed = workspace.upload_file_preview_to_data_volume(catalog_name, database_name, volume_name, local_file_path)
volume = workspace.attach_data_volume_workflow(catalog_name, database_name, volume_name, workflow_id)
volume = workspace.detach_data_volume_workflow(catalog_name, database_name, volume_name, workflow_id)
path = volume.full_path()
refs = volume.refs()
files = volume.files(sdk.with_file_list_page_size(file_list_page_size))
processed_files = volume.processed_files(sdk.with_processed_volume_files_limit(processed_files_limit))
path = workspace.data_volume_full_path(catalog_name, database_name, volume_name)
refs = workspace.data_volume_refs(catalog_name, database_name, volume_name)
folder, created_folder = volume.create_folder(folder_name, sdk.with_folder_description(folder_description))
folder = folder.rename(renamed_folder_name, sdk.with_updated_folder_description(updated_folder_description))
folder_refs = folder.refs()
folder.clean()
folder.delete()
info = file.info()
file = file.rename(renamed_file_name)
download = file.download(sdk.with_file_as_zip(download_as_zip))
download.close()
preview_stream = file.preview()
preview_stream.close()
excel_preview = file.preview_excel(sdk.with_excel_sheet_name(excel_sheet_name))
data_asset = file.data_asset()
file_artifact = file.artifact()
# First deployment: let the server allocate the ID. Pass an existing ID to publish a new version.
workflow, deployed = workspace.deploy_workflow(workflow_name, dsl_yaml)
workflow_id = workflow.id
workflow = workspace.workflow(workflow_id)
run_data = workflow.run(sdk.with_workflow_run_input(workflow_run_input))
file_lineage = file.lineage_overview()
artifact = workspace.artifact(artifact_id)
artifact_blocks = artifact.output_blocks()
artifact_node = artifact.node(node_id)
node_rerun = artifact_node.rerun(sdk.with_lineage_rerun_mode(lineage_rerun_mode))
run = workflow.run_handle(execution_id)
run_node = run.node_handle(node_key)
rerun_plan = run_node.rerun_plan(sdk.with_source_node_execution_id(node_execution_id)).plan
created_rerun = run_node.create_rerun(workflow_rerun_mode, node_execution_id, sdk.with_expected_workflow_rerun_contract_hash(rerun_plan.rerun_contract_hash))
rerun = run.rerun(rerun_id)
rerun_info = rerun.info()
result = run.result()
cancelled = run.cancel(sdk.with_workflow_cancel_reason(workflow_cancel_reason))
operator_spec = sdk.CustomOperatorSpec(operator_name, operator_identifier, operator_description, input_schema, output_schema)
operator, created_operator = workspace.create_custom_operator_from_spec(operator_spec)
tested_operator = operator.test_with_input(sdk.CustomOperatorTestInput(operator_test_input))
workflow_template, created_template = workspace.create_workflow_template(workflow_template_name, dsl_yaml)
workflow_template_info = workflow_template.info()
service = workspace.workitem_api_service(node_id, service_version)
published_service = service.publish(sdk.WorkitemAPIServicePublishSpec(service_version, compute_resource_id=compute_resource_id, timeout_seconds=service_timeout_seconds, max_concurrency=service_max_concurrency, rate_limit_per_min=service_rate_limit_per_min))
invoked_service = service.invoke(sdk.WorkitemAPIServiceInvokeSpec(service_name, service_type, service_version, service_payload))
session, created = workspace.create_explore_session(explore_session_title)
session = workspace.explore_session(explore_session_id)
explore_data = workspace.explore_data()
overview = explore_data.overview()
explore_database = explore_data.database(database_id, explore_database_name)
explore_tables = explore_database.tables()
explore_table = explore_database.table(table_id, explore_table_name)
columns = explore_table.columns()
sources = sdk.ExploreDataSources().with_table(explore_database_name, [explore_table_name], catalog_id).with_semantic_models(semantic_model_id)
answer = session.query_with_sources(explore_question, sources)
messages = session.messages(sdk.with_explore_message_limit(explore_message_limit))
latest = session.latest_message_id()
message = session.message(message_id)
liked = message.like()
semantic_model, created_model = workspace.create_semantic_model(semantic_model_name, sdk.with_semantic_model_tables([table_name]))
semantic_entry, created_entry = semantic_model.create_entry(sdk.SemanticEntryInput(semantic_entry_kind, semantic_entry_key, semantic_entry_spec, [table_name]))
validated_model = semantic_model.validate()
exported_model = semantic_model.export()
connector, created_connector = workspace.create_connector(connector_name, source_type, usage_type)
connector = workspace.connector(connector_id)
source_databases = connector.source_databases()
source_schemas = connector.source_schemas(source_schema_name)
source_tables = connector.source_tables(source_schema_name)
source_schema = connector.source_schema(source_schema_name, table_name)
target_databases = connector.mo_databases()
target_tables = connector.mo_database_tables(target_database_name)
target_table_exists = connector.check_mo_table_name(target_database_name, table_name)
column_mapping = connector.mo_column_mapping(target_database_name, table_name, column_mapping_input)
connector_file = connector.file(connector_file_id)
preview = connector_file.preview(sdk.with_connector_preview_row_start(connector_preview_row_start))
download_url = connector_file.download()
stream = connector_file.stream()
stream.close()
connector_file.delete()
import_task, imported = connector.create_file_import_task(sdk.FileImportTaskSpec(config_type, import_task_uris, load_mode_config, file_filter_config, name=import_task_name, volume_id=volume_id))
import_task.update_config(sdk.ImportTaskUpdateSpec(load_mode_config, name=import_task_updated_name, file_filter_config=file_filter_config, uris=updated_import_task_uris))
import_runs = import_task.runs()
import_task.retry_files(file_id)
export_task, exported = connector.create_export_task_from_spec(sdk.ExportTaskSpec(export_task_name, connector_name, export_type, sdk.ExportTaskConfig(s3_config=s3_config), [sdk.ExportTaskFile(file_id, export_file_path)]))
export_state = export_task.state()
export_task.retry(file_id)
agent = workspace.agent_by_code(agent_code)
agent_task = agent.send_text(sdk.AgentTextMessage(agent_prompt, agent_message_id, request_id=request_id))
agent_task_id = sdk.agent_a2a_task_id(agent_task)
agent_task_status = agent.get_task(sdk.AgentTaskRequest(agent_task_id, request_id=status_request_id))
agent_turn_id = sdk.agent_a2a_turn_id(agent_task)
agent_input = agent.submit_input(sdk.AgentInputSubmission(agent_task_id, agent_turn_id, agent_input_answers, request_id=input_request_id))
llm = workspace.llm_provider()
llm_backend, created_llm = llm.create_backend(provider_backend_name, sdk.with_provider_backend_address(model_endpoint), sdk.with_provider_backend_models(*provider_model_names))
models = llm_backend.probe_models(sdk.with_provider_backend_api_key(api_key))
endpoints = llm_backend.endpoints()
router = llm.router().update(sdk.with_router_strategy(router_strategy))
embedding = workspace.embedding_provider()
embedding_backend, created_embedding = embedding.create_backend(embedding_backend_name, sdk.with_provider_backend_models(*embedding_model_names))
embedding_models = embedding_backend.probe_models()
parser = workspace.parser_provider()
parser_backend, created_parser = parser.create_backend(parser_backend_name, sdk.with_provider_backend_supported_mime_types(*supported_mime_types))
group = workspace.alert_group(alert_group_id)
workspace.create_alert_receiver(group.id, receiver_name, notify_type, receiver_status, sdk.with_receiver_email(receiver_email))
receiver = workspace.alert_receiver(receiver_id)
workspace.create_alert_rule(expression_id, alert_level, alert_category, sdk.with_alert_rule_receivers(receiver.id))
rule = workspace.alert_rule(alert_rule_id)
history = group.history(sdk.with_alerting_page(alerting_page), sdk.with_alerting_size(alerting_size))
group.mark_read()
rule.update(sdk.with_alert_rule_update_level(updated_alert_level))
receiver.update(sdk.with_receiver_update_status(receiver_update_status))
compute, created_compute = workspace.create_compute_resource(worker_image, spec_id, compute_cpu, compute_memory_gb, sdk.with_compute_min_replicas(compute_min_replicas), sdk.with_compute_max_replicas(compute_max_replicas))
preflight = compute.preflight_delete()
suspended = compute.suspend()
resumed = compute.resume()
compute.delete(sdk.with_force(compute_force_delete))
table_scope = sdk.DataShareScope(mode="selected", object_ids=source_table_ids)
publish, created_publish = workspace.create_data_share_publish(publish_name, source_database_id, table_scope, [target_workspace_id], sdk.with_data_share_remark(data_share_remark))
summary = workspace.data_share_summary()
publish = workspace.data_share_publish(publish_id)
updated_publish = publish.update(sdk.with_data_share_update_table_scope(table_scope))
subscription = workspace.data_share_subscription(subscription_id)
subscribed = subscription.subscribe(subscription_name)
subscription.unsubscribe()
publish.delete()
sql_metadata = workspace.sql_metadata()
sql_databases = sql_metadata.databases()
sql_tree = sql_metadata.tree()
sql_database = sql_metadata.database(target_database_name)
sql_tables = sql_database.tables()
sql_table = sql_database.table(table_name)
sql_columns = sql_table.columns()
sql_ddl = sql_table.ddl()
workbook, created_workbook = workspace.create_sql_workbook(sql_workbook_name)
version, created_version = workbook.create_version(sql_text)
version.save()
query, started_query = workspace.execute_sql(sql_text, sdk.with_sql_query_db_name(target_database_name))
query_state = query.describe()
statement = workspace.sql_statement(statement_id)
rows = statement.result(sdk.with_sql_result_limit(sql_result_limit))
profile = statement.profile()
catalog = catalog.rename(renamed_catalog_name)
database = database.rename(renamed_database_name)
table_path = table.full_path()
table_refs = table.refs()
table.truncate()
table.delete()
volume = volume.rename(renamed_volume_name)
catalog_info = catalog.info()
database_info = database.info()
volume_info = volume.info()
catalog_refs = catalog.refs()
database_refs = database.refs()
file.delete_ref()
file.delete()
volume.delete()
database.delete()
catalog.delete()
failures = workspace.recent_failed_audit_logs(recent_audit_limit)
`

## SQL result download API contract after PR #14017

The Python Product SDK does not currently expose a helper for SQL result
downloads. Consumers that call the backend directly must use:

```text
POST /newmoi/query/result/download
{"statement_id":"<owned saved-result statement ID>"}
```

Use the normal Product API authentication and workspace context. Get
`statement_id` from SQL execution or query history. A missing ID is rejected,
and the server does not re-execute SQL text or accept `query` / `db_name` as a
compatibility fallback.

The route returns a streamed CSV response. The calling Python HTTP client owns
the response stream and must consume and close it. This repository change does
not add a Python SDK method, modify SDK version metadata, or publish a package.
