# MOI 业务权限模型 Registry 快照

> 类型：Core Registry 的派生查阅快照，不是运行期事实源
>
> `registry_schema_version`: `iam.registry.m40.v1`
> 源：`moi-core/catalog/pkg/iamcore/canonical_registry.go`

运行期以 `NewCanonicalIAMRegistry()`、Core Authorize/ResourceAccessFilter 和 owner resolver 为准。本文不得被 Backend、Frontend、SDK 或 Worker 解析成 allow 规则。

查询业务功能/API 对应的 action、workspace/object 授权层级、Ownership 和依赖资源时，必须阅读[业务功能权限模型目录](08-business-permission-model-catalog.md)。当前不属于 canonical 产品资源的边界见[业务权限模型例外登记](10-business-permission-model-exceptions.md)。

核对命令：

```bash
cd moi-core/catalog
go test ./pkg/iamcore -run 'TestCanonicalIAMRegistry|TestIAMRouteActionCoverageChecker' -count=1
go run ./cmd/iam-route-action-checker
```

## 1. Canonical 资源

<!-- iam-registry-resources:start -->

| Resource type | 产品对象 | 语义分册 |
| --- | --- | --- |
| `workspace` | workspace 范围的治理、概览、历史与 create parent | [业务目录：Workspace 与治理](08-business-permission-model-catalog.md#3-workspace成员与-role) |
| `role` | workspace Role | [业务目录：Role](08-business-permission-model-catalog.md#34-rolepolicy-与-role-graph) |
| `connector` | 数据连接器 | [业务目录：Connector](08-business-permission-model-catalog.md#41-connector) |
| `workflow` | Workflow 应用对象 | [业务目录：Workflow](08-business-permission-model-catalog.md#42-workflow) |
| `api_service` | 已发布的 WorkItem API Service | [业务目录：API Service](08-business-permission-model-catalog.md#44-api-service) |
| `compute_resource` | 工作区计算资源实例 | [业务目录：Compute Resource](08-business-permission-model-catalog.md#45-compute-resource) |
| `catalog` | Catalog 层级对象 | [业务目录：Catalog](08-business-permission-model-catalog.md#51-catalog) |
| `database` | Database 层级对象 | [业务目录：Database](08-business-permission-model-catalog.md#52-database) |
| `volume` | Volume/文件根资源 | [业务目录：Volume 与文件](08-business-permission-model-catalog.md#53-volume-与文件) |
| `table` | Table 元数据和数据访问目标 | [业务目录：Table 与 MatrixOne](08-business-permission-model-catalog.md#54-table-与-matrixone) |
| `data_task` | 数据任务 | [业务目录：Data Task](08-business-permission-model-catalog.md#61-data-task) |
| `export_task` | 导出任务 | [业务目录：Export Task](08-business-permission-model-catalog.md#62-export-task) |
| `semantic_model` | 语义模型/知识库对象 | [业务目录：Semantic Model](08-business-permission-model-catalog.md#63-semantic-model) |
| `data_publish` | Data Share 发布 | [业务目录：Data Publish](08-business-permission-model-catalog.md#81-data-publish) |
| `data_subscription` | Data Share 订阅 | [业务目录：Data Subscription](08-business-permission-model-catalog.md#82-data-subscription) |
| `model_backend` | LLM/Embedding/Parser backend | [业务目录：Model Backend](08-business-permission-model-catalog.md#71-model-backend) |
| `agent` | 产品级 Agent 对象 | [业务目录：Agent](08-business-permission-model-catalog.md#72-agent) |
| `plugin_release` | 不可变 Agent 插件发布版本 | [业务目录：Agent Plugin](08-business-permission-model-catalog.md#722-agent-plugin) |
| `plugin_installation` | 工作区或个人插件安装 | [业务目录：Agent Plugin](08-business-permission-model-catalog.md#722-agent-plugin) |
| `plugin_connection` | Agent 插件外部身份连接 | [业务目录：Agent Plugin](08-business-permission-model-catalog.md#722-agent-plugin) |
| `agent_sandbox` | 托管 Agent Sandbox 执行器 | [业务目录：Sandbox 与 Runner](08-business-permission-model-catalog.md#73-agent-sandbox-与-runner) |
| `agent_runner` | 自定义 Agent Runner 执行器 | [业务目录：Sandbox 与 Runner](08-business-permission-model-catalog.md#73-agent-sandbox-与-runner) |
| `agent_team` | 显式 MOI Agent Team | [业务目录：Agent Team 与 IngressConnection](08-business-permission-model-catalog.md#722-agent-team-与-channel-ingress) |
| `ingress_connection` | 外部 Bot/App/邮箱到 Agent/Team 的受控双向通信连接 | [业务目录：Agent Team 与 IngressConnection](08-business-permission-model-catalog.md#722-agent-team-与-channel-ingress) |
| `workbook` | SQL Editor Workbook | [业务目录：Workbook](08-business-permission-model-catalog.md#74-workbook-与-sql-editor) |
| `data_dashboard` | 手写 SQL Data Dashboard | [业务目录：Data Dashboard](08-business-permission-model-catalog.md#75-data-dashboard) |
| `custom_operator` | 用户自定义 Workflow Operator | [业务目录：Custom Operator](08-business-permission-model-catalog.md#43-custom-operator) |

<!-- iam-registry-resources:end -->

Workspace Member、Default Role、subject attribute 和 audit 是 workspace 治理事实/操作，不以独立对象资源类型加入上述 Registry 列表。Model Router 的 action 作用于 workspace 级配置。A2A、WorkItem Catalog、临时候选文件和 session/message 不是 canonical 产品资源。

<!-- iam-registry-actions:start -->

## 2. Workspace 治理与平台 Action

| Domain | Canonical action IDs |
| --- | --- |
| Query History | `query_history.read`, `query_history.audit.read` |
| Role | `role.read`, `role.audit.read`, `role.create`, `role.update`, `role.delete`, `role.lifecycle.mutate`, `role.manage_inheritance` |
| Workspace Member | `workspace_member.read`, `workspace_member.invite`, `workspace_member.update`, `workspace_member.subject_attribute.manage`, `workspace_member.role_binding.mutate`, `workspace_member.lifecycle.mutate`, `workspace_member.delete`, `workspace_member.audit.read` |
| Ownership | `resource.ownership.repair` |
| Model Router | `model_router.read`, `model_router.update` |

## 3. 应用资源 Action

| Resource | Canonical action IDs |
| --- | --- |
| `connector` | `connector.create`, `connector.read`, `connector.update`, `connector.delete`, `connector.use` |
| `workflow` | `workflow.create`, `workflow.read`, `workflow.update`, `workflow.delete`, `workflow.run`, `workflow.manage`, `workflow.manage_tag`（workspace 范围，标签及值 CRUD） |
| `compute_resource` | `compute_resource.create`, `compute_resource.read`, `compute_resource.update`, `compute_resource.delete`, `compute_resource.use`, `compute_resource.operate` |
| `data_task` | `data_task.create`, `data_task.read`, `data_task.update`, `data_task.delete`, `data_task.operate` |
| `export_task` | `export_task.create`, `export_task.read`, `export_task.delete`, `export_task.retry` |
| `finetune_job` | `finetune_job.create`, `finetune_job.read`, `finetune_job.cancel` |
| `semantic_model` | `semantic_model.create`, `semantic_model.read`, `semantic_model.update`, `semantic_model.delete`, `semantic_model.use` |
| `model_backend` | `model_backend.create`, `model_backend.read`, `model_backend.update`, `model_backend.delete` |
| `agent` | `agent.create`, `agent.read`, `agent.update`, `agent.delete`, `agent.use` |
| `plugin_release` | `plugin_release.read` |
| `plugin_installation` | `plugin_installation.create`, `plugin_installation.read`, `plugin_installation.update`, `plugin_installation.delete`, `plugin_installation.use` |
| `plugin_connection` | `plugin_connection.create`, `plugin_connection.read`, `plugin_connection.update`, `plugin_connection.delete`, `plugin_connection.use` |
| `agent_sandbox` | `agent_sandbox.create`, `agent_sandbox.read`, `agent_sandbox.update`, `agent_sandbox.delete`, `agent_sandbox.terminal`, `agent_sandbox.use` |
| `agent_runner` | `agent_runner.create`, `agent_runner.read`, `agent_runner.manage`, `agent_runner.delete`, `agent_runner.use` |
| `agent_team` | `agent_team.create`, `agent_team.read`, `agent_team.update`, `agent_team.delete` |
| `ingress_connection` | `ingress_connection.configure`, `ingress_connection.read` |
| `workbook` | `workbook.create`, `workbook.read`, `workbook.update`, `workbook.delete` |
| `data_dashboard` | `data_dashboard.create`, `data_dashboard.read`, `data_dashboard.update`, `data_dashboard.delete`, `data_dashboard.use` |
| `custom_operator` | `custom_operator.create`, `custom_operator.read`, `custom_operator.update`, `custom_operator.delete`, `custom_operator.run`, `custom_operator.use` |
| `api_service` | `api_service.read`, `api_service.publish`, `api_service.manage`, `api_service.run` |

## 4. Catalog 与数据 Action

| Resource | Canonical action IDs |
| --- | --- |
| `workspace` | `workspace.create_catalog`, `workspace.show_catalogs` |
| `catalog` | `catalog.update_catalog`, `catalog.delete_catalog`, `catalog.create_database`, `catalog.show_databases` |
| `database` | `database.update_database`, `database.delete_database`, `database.show_tables`, `database.show_volumes`, `database.create_volume`, `database.create_table`, `database.grant.create_table`, `database.query`, `database.grant.query` |
| `volume` | `volume.read`, `volume.update`, `volume.delete`, `volume.write` |
| `table` | `table.query`, `table.insert`, `table.update`, `table.delete`, `table.grant.query`, `table.grant.insert`, `table.grant.update`, `table.grant.delete` |

Catalog 树的 operation requirement 必须以 Registry 为准：`workspace.create_catalog` 在 Workspace 上只接受 `all`，`database.create`（已发布别名 `catalog.create_database`） 支持指定 Catalog 或 `all` 创建父 scope，`database.create_volume` 和 `database.create_table` 在父 Database 上授权；Catalog/Database 更新和删除分别使用 `catalog.update_catalog` / `catalog.delete_catalog` 与 `database.update_database` / `database.delete_database`。不能仅根据 action 前缀假设目标资源已经存在。

Catalog 建库范围只约束 MOI API；上述任一建库授权会向对应 MO Role 同步账号级 `CREATE DATABASE`，SQL 直连和 SQL Editor 不按 MOI Catalog 范围限制建库。

普通应用对象的创建、查看 action 只允许当前 workspace 的全局授权，当前 workspace 本身的 exact scope 仍表示全局能力。Catalog 数据树例外：Database、Volume、Table 的查看允许指定对象，创建按真实父容器 scope 授予；Table 的建表与查询对齐 MatrixOne 权限。

`database.show_tables` 和 `database.show_volumes` 是 Database 父级的子项导航 action，支持 `all` 或指定 Database。它们不能替代具体对象的查看授权；具体 Table 的 SELECT 与元数据仍由 `table.query` 负责，具体 Volume 及其文件层级仍由 `volume.read` 负责。

`database.create_table`、`table.query`、`table.insert`、`table.update`、`table.delete` 是 MatrixOne DCL 对齐 action；Table 创建只在父 Database 上使用 `database.create_table`，不再另设旧名称 table.create。`*.grant.*` action 表示配置到目标 Role 的对象级可委派能力，和 MatrixOne DCL 的 `WITH GRANT OPTION` 是不同层次的事实：MOI `role.create` 或 `role.update` 可管理任意对象权限；没有该大权限时，当前对象 Owner 的 WGO 语义只覆盖自己拥有的 exact 对象。Core 仍校验目标 action、exact scope、目标 Role 生命周期和 CAS。

## 5. Data Share Action

| Resource | Canonical action IDs |
| --- | --- |
| `data_publish` | `data_publish.create`, `data_publish.read`, `data_publish.update`, `data_publish.delete` |
| `data_subscription` | `data_subscription.create`, `data_subscription.read`, `data_subscription.delete` |

<!-- iam-registry-actions:end -->

## 6. 更新检查

发现以下任一变化时必须更新本快照：

- `IAMRegistrySchemaVersion`；
- `IAMResource*` 或 `IAMAction*` 常量；
- `NewCanonicalIAMRegistry()` 注册或删除 resource/action。

`go run ./cmd/iam-route-action-checker` 会精确比较本文件标记区间内的 resource/action 集合和 Registry schema。operation requirement、route binding、create parent、Role graph inheritance、resolver 与 collection default read action 不在本文复制，由 Registry tests、route checker 和[业务功能权限模型目录](08-business-permission-model-catalog.md)证明。
