# MOI IAM 当前实现状态

> `verified_against_commit`: `81209e79d71ad665708381a22180c0049d0b6166`
>
> `verified_on`: `2026-08-30`
> Core Registry schema: `iam.registry.m38.v1`

本文只记录在上述代码基线可由生产代码与测试证明的实现状态，不定义授权模型。代码行为变化后必须按 [验证与漂移控制](06-verification-drift-control.md) 重新核对并更新基线。

2026-10-24 已确认[权限失败语义](01-product-authorization-model.md#9-失败语义)：可控授权异常按无权限处理并隔离影响范围，不再将 `fail closed` 等同于系统错误或整页阻断。本次只更新设计与接入规则，未修改生产行为，不能记为已完成验收。当前 native [`writeIAMFrameworkError`](../../moi/pkg/api/handlers/iam_error.go) 仍将 `ErrSnapshotStale` 与不可用错误一起映射为 `503`；[`Current Principal projector`](../../moi/pkg/service/iam/platform/current_principal.go) 仍需按受影响事实核对投影隔离。后续实现按[定向验收要求](06-verification-drift-control.md#33-拒绝分类与故障隔离验证)逐项核对，不因本次规范更新宣称全链路已符合。

2026-10-15 的 MOI 单进程工作树增量修正了正常创建/删除的一致性合同：业务与 canonical Ownership 必须共同完成，同库使用同一事务，跨库复用原持久操作，失败不能报告成功。当前 `moi/pkg/composition/generator` 和通用 mutation coordinator 均拒绝 `after_commit`。下表相应行只更新这一增量；其它 Core/Backend 历史证据仍属于原基线，不能据此宣称重新完成了真实环境验证。

2026-10-18 的普通角色删除增量在确认 MatrixOne Role 缺失后，于最终 tenant transaction 硬删角色及运行期授权元数据，同时保留原名删除回执和审计。offset183 幂等清理历史普通 deleted 角色，保留系统墓碑；名称列维持 `VARCHAR(255)`，已移除内部名称归档格式。可信 DAO 的角色缺失按已删除拒绝授权，租户连接或存储错误仍不可用。Data Privilege 和 Ownership 新写共享 Role 删除行锁，删除检查阻止仍 applying 的数据权限操作。角色缺失与事务故障分类、回执重放及缺角色写入的定向回归已验证；现有 MatrixOne 隔离临时库验证了实际删除 DAO 的旧红/新绿、回滚原子性、同名重建、回执/审计保留，以及实际 offset183 与产品迁移 fixture 的幂等清理和物理残留拒绝。Data Share 撤销统一在 Ownership 写入前取得相关 Role 锁，Owner Role 已删除时仍清理其他 Role 的对象授权；Data Privilege 持久请求仅增加缺失或已删除 Role 的写入保护，保留原有生命周期准入；单资源撤销与角色硬删除的真实 MatrixOne 并发用例已完成旧红/新绿验证。Product SDK 双认证删除、审计和最终收尾失败回归已补充并完成编译；本地未运行完整集成环境，当前增量的全链路验证交由 CI。

2026-10-19 的角色删除转移增量已在当前工作树实现：删除预检返回绑定完整集合版本的分页对象清单，弹窗支持转给当前角色、指定角色和逐对象选择。转移请求通过生成边界同时校验 `role.delete` 与 `role.update`，首次执行、自动重试和重启恢复中的实际转移均重新鉴权；目标角色、Ownership CAS、逐项审计和本地硬删除共用事务，转移后的 Ownership 保留。DAO、Service、前端和 SDK 定向用例及双认证 Product SDK 集成场景已补充；本轮未运行真实 MatrixOne 完整集成环境，不能据此宣称转移全链路已验收。

2026-10-19 的 `codex/iam-permission-consistency` 本地工作树增量已将独立 Data Privilege apply 收敛到现有 Saga 的 MO 执行／读回与 MOI 提交两个步骤；MOI 使用持久化有限重试预算，生产装配不再注册独立权限持续扫描。repair 只导入 MO 当前事实；后续增量已将同 Role 的冲突隔离收敛到仍在执行的 `applying`，`unknown|drifted|failed` 结果不阻止新保存。已确认 Saga 失败的遗留占用由同一 owner 在失败返回或下一次编辑时释放，旧操作不能覆盖后续保存。角色编辑与独立 apply 接受省略业务 `request_id`，角色编辑前端按当前草稿重新提交；正常 DCL 去除了仅为相等比较的整套权限预读，保留写后确认。证据入口为 `moi/pkg/service/iam/data_privilege_saga.go`、`data_privilege_mutation.go`、`role_update.go` 和 `IAMRolePermissionEditor.tsx`；已补充对应 Service、DAO 和 Product SDK 定向回归；完整集成验证交由 CI。

同日的整角色 PATCH 增量已完成相同收敛：无 MO 权限变化时直接用本地事务；跨 MO 边界时由一个聚合 Saga 先确认 MO，再原子提交 Policy、数据投影、角色元数据、版本、审计和成功回执。已删除旧快照反向补偿及 PATCH 数据权限子操作的独立恢复分支，复用现有 Repository、Role 占用和 Saga 持久预算。定向回归覆盖本地回滚、重复保存、历史回执、提交确认丢失、活跃租约拒绝接管、中断后的只读确认及 MOI 收尾失败；Product SDK 用例已同步，完整集成验证交由 CI。

2026-10-21 的整角色编辑收敛已移除普通保存中的旧操作接管、旧资源合并和旧权限导入。`SagaRecoveryRunner` 统一分发整角色编辑和独立数据权限，中断恢复沿用原执行 fence 与剩余预算，预算耗尽留给 owner 管理员处理；确认失败后释放占用，新保存只执行当前输入。旧格式独立 `applying` 记录继续兼容原 intent/hash，新保存只释放历史占用，当前事实同步由显式 repair 完成。统一人工介入接口和后台管理另行提供，本次未新增管理入口。已补充共享恢复、预算耗尽、过期 claim、新保存隔离和历史记录的定向回归；本轮本地仅执行定向检查，真实 Product SDK 场景更新后交由 CI 验证，本地 MatrixOne 容器已停止，不能宣称本轮全链路通过。统一设计标准见[存储合同 §4.1](04-storage-lifecycle-audit.md#41-事务与持久恢复边界)和[公开合同 §1.1](07-public-api-frontend-sdk-contracts.md#11-保存与重试的统一原则)。

本次数据树请求计划增量以 `upstream/dev@0aced71bf17024b48465bbbdff7ad683d8563b6c` 为实现基线：BFF `coreclient` 活跃请求状态与 SDK transport decorator、Core `iamcore/catalog_authorization_request.go`、内部签名合同、Root Volume 批量门禁及契约测试已接入。该条目仅更新本次范围，不表示重新验证整份历史状态表。 文件入口进一步收敛为 Core Volume owner 的批量准备接口：BFF 不再逐 Root 重复执行普通 Authorize；准备阶段复用入口 Verified Effective Role，并补齐失败审计、诊断日志和公开错误分类。

A2A 会话持久化 owner 已建立独立授权生命周期，覆盖 HTTP 返回、SSE 断连、写入确认及消息/事件/标题保存，并在操作结束时关闭。请求级集合计划只传完整 query shape 与去重的来源分类；`catalog_authorization_request_test.go` 覆盖 2000 个 Volume 的 Owner、显式 grant 和混合范围，证明精确范围、无额外 PDP 的复用及与点授权的隔离。

统一准入与数据树计划已共用 filter 的匹配和发布入口，首次合并 filter 保留身份事实复用，并将已完成的数据树集合范围写入请求计划。`principal_admission_catalog_plan_test.go` 覆盖 Verify、合并 Authorize/filter 的角色来源与版本、请求内固定身份和新请求撤权，以及集合范围跨子请求复用、Owner ID 冻结和新 action/point 隔离；QA 发布后的耗时与 SQL 计数仍待验证。

2026-10-19 Catalog 创建权限按父 scope 收敛：`database.create`（已发布别名 `catalog.create_database`） 接受指定 Catalog 和 `all`，MOI 建库入口以可信父 Catalog 调用 Core。任一有效建库策略都向对应 MO Role 物化账号级 `CREATE DATABASE`；SQL 直连与 SQL Editor 不应用 MOI Catalog 范围。创建沿用当前有效 Role 的连接，MO 物理 Owner 与 MOI Ownership 使用同一 Role。移除最后一条建库策略后，既有 Role 写入流程回收该 DCL 权限；仅校验策略不改变 DCL。Volume 创建沿用实际父节点 Database；Table 创建由 `database.create_table` 对齐 Database 级 MO DCL。定向 Registry/策略投影测试已通过；Product SDK + SQL 双入口回归已补充并编译通过。本地完整环境此前在创建共享测试 workspace 阶段超时，未得到端到端行为验证结果。对象授权入口和删除 Catalog 时的 specific grant 清理已接入同一 MO 建库权限投影：授予在策略提交后同步，移除最后一条建库授权前先回收 DCL，历史重放按当前持久策略同步；DCL 撤销失败时保留原策略并返回错误。该次增量已通过当前策略重放、停用 Role、最后一条授权清理及撤销失败的定向测试，真实 MatrixOne 双入口回归仍交由 CI 验证。

2026-10-20 补齐 Catalog 删除清理建库授权的持久恢复：撤销 DCL 前保存 Saga intent，确认回滚后立即恢复；提交结果不明或进程重启后，由既有 IAM 后台入口在 Role 行锁下按当前持久策略重新同步。复用标准 Saga 执行器、持久预算和存储，不改变上游 Role 删除 Saga。策略写入、Ownership 收尾、请求取消、提交拒绝与提交回执丢失、恢复失败终态、新策略及已删除 Role 的定向回归已通过。已补充 API key / bearer token 的 Product SDK Catalog 删除失败回归；本地尝试在环境启动阶段因缺少 Java Runtime 失败，未执行到该接口场景，真实 MatrixOne 全链路结果仍待 CI。

2026-10-19 退休未迁入 native 的 `memory_observability.read`、`memory_audit.read`，以及不再单独判权的 `resource.ownership.transfer`。当前 Registry、权限 Schema 和前端权限分类不再提供它们；Memory 监控/审计页签与专用 API 引用同步删除。历史策略仍先校验文档、索引和身份事实，已退休条目不参与运行期授权、不出现在角色权限视图中，下一次成功保存角色时从策略文档和索引一并清理；失败回滚保留原快照。冻结升级 Registry 只保留历史数据解释用途，不恢复这些权限。

Ownership 登记和 Owner 授权机制保留；转移规则明确为对象 Owner 或具有 `role.update` 的角色可操作，不新增独立 action。native 当前通过角色删除流程支持转移该 Role 名下的对象，要求同时具备 `role.delete` 与 `role.update`；本分支新增面向角色管理员的独立对象 Owner 转移入口与 Go/Python SDK，使用 `role.update`、目标 Role 行锁、版本 CAS 和事务内审计回执。前端支持直接从删除清单打开具体对象、转移成功后返回，以及用户和对象各自按总量分页。两种全部转移按页读取、逐对象提交，失败保留已成功部分并显示进度，完成后单独删除角色；未新增集合版本标记优化。总量统一从删除影响检查读取，对象页使用独立的 `delete-ownerships` 入口，翻页不重新统计；旧组合接口复用影响总数。普通 Owner 单独准入仍未在此管理入口开放。真实 TCP + MatrixOne 已验证管理员转移、权限拒绝、幂等重放、旧版本冲突、原角色保留与后续删除；大数据量性能测试因本地 MatrixOne 反复退出和连接中断尚未完成，不能记为性能验收通过。

## 1. 状态枚举

| 状态 | 含义 |
| --- | --- |
| `implemented` | 生产链路和对应测试已存在 |
| `transition-membership-only` | 当前明确只要求 Verified Effective Role，不代表对象授权 |
| `transport-only` | 只消费已确认的可信 BFF/内部 transport 与 tenant 上下文，不产生产品对象 action allow |
| `blocked-unsupported` | 产品入口应拒绝或不存在，尚未定义可执行合同 |
| `runtime-gap` | admission 已接入，但部分实际运行期依赖尚未动态重验 |
| `contract-gap` | 生产路径已存在，但仍有已验证行为与当前规范合同冲突，不能宣称闭环 |
| `cleanup-gap` | 新权限主链路已生效，但仍有明确登记的 legacy 物理资产、公开兼容入口或发布验收待删除/补齐 |
| `poc-not-productized` | POC/内部能力，尚不是 canonical 产品权限资源 |
| `retired` | 旧事实或入口已从生产授权链删除，不得恢复 |

## 2. 核心能力

| Capability | Status | Production evidence | Test/gate evidence | Known limitation |
| --- | --- | --- | --- | --- |
| 唯一 Effective Role 验证 | `implemented` | `moi-core/catalog/pkg/iamcore/effective_role.go` | `effective_role_test.go` | 无本地 fallback |
| Core point Authorize | `implemented` | `iamcore/authorizer.go`, `authorize_boundary.go` | `authorizer_test.go`, `authorize_boundary_test.go` | Core 不可用 fail closed |
| Core collection filter | `implemented` | `iamcore/resource_access_filter.go`, `resource_picker.go` | 对应测试覆盖 filter/owner/pagination | 调用方仍需按资源逐 route 接入 |
| 同步请求身份与统一准入 | `implemented` | 本地未发布：VerifiedPrincipal、公共 WorkspaceAdmission、轻量 verifier、Authorize/filter 合并、请求内 fact bag 与 owner 投影复用；见 [12](12-request-principal-admission.md) | 816/816 workspace 入口显式登记，canonical 288/288；813 个入口首次准入拒绝零 tenant/业务 I/O，另 3 个投影入口专项回归；Core 事实/fence、角色固定、main 顺序、AST 构造边界和 SDK 路由对账 | 未部署；CI 跨服务、版本组合及 QA 性能验收未执行。44 个既有账号/平台/协议入口保留独立边界；详情见[实施计划](plans/request-principal-admission.md) |
| Workspace 治理列表无权空集合 | `implemented` | Backend `iampep/workspace_collection.go`、`handlers/iam/iam.go`、`workspacemember/service_user.go` | `workspace_collection_test.go` 与两个 handler 的 `collection_visibility_test.go` | 成员、标签定义、角色列表只将明确的 `PERMISSION_DENIED` 转为 `200` 空数组；保留身份、Role lifecycle 和依赖故障，拒绝后不读取治理数据 |
| Core owner access planning / bounded action projection | `contract-gap` | `iamcore/resource_access_filter.go`, `owner_access_plan.go`, `batch_resource_action_projection.go`, `principal_access_facts.go`, tenant strict exact-ID Ownership reader | `resource_access_filter_test.go`, `owner_access_plan_test.go`, `batch_resource_action_projection_test.go`, `iam_ownership_test.go` | canonical action `all` 与 system all-access 已不读 target Ownership，显式 exact scope 也不附加 Ownership；但 mixed/Owner plan 的 `addRoleOwnedResources`、`validateActiveOwnershipCandidate` 和 inventory validation 仍会把 non-active/畸形/冲突 Ownership 升级为整个请求的 adapter error。目标是这些记录只产生 no-match + 结构化日志；只有 Owner reader 不可用或已采用 active proof 漂移时才使依赖该 Owner 来源的计划失败 |
| canonical Registry/route binding | `implemented` | `iamcore/canonical_registry.go` | `canonical_registry_test.go`, `cmd/iam-route-action-checker` | 索引文档只是派生快照 |
| Backend 统一 PEP/Core client | `implemented` | `moi-backend/pkg/iampep`、`pkg/coreclient`；Catalog `pkg/api/backendauth`/`pkg/api/requestauth` 解析可选 execution metadata | Backend middleware/transport/architecture tests；Catalog route contract tests | 可信 BFF 的非数据树 Catalog 调用无需 execution contract，Catalog 直接信任且不重复授权；`bff_complete_pep` 携带真实 canonical facts 供审计；`coreclient` 只校验调用方明确发送的合同，不按 URL 推断；真实数据树使用 receiver-PDP transport 并在 own PDP/filter 前屏蔽 BFF trust |
| Worker sender / Catalog receiver（已登记入口） | `implemented` | go-worker `pkg/runtime/client_factory.go`、Backend `pkg/worker/execution_user.go`、embedded/proxy Task handler；普通 receiver 使用最小身份 transport，`moi:workflow.trigger -> POST /tasks` 使用专用 sender 发送 `workflow_trigger_task_v1` 元数据 | client factory、WorkItem、execution user、Task 与跨服务边界测试 | continuation 只约束登记 sender 的调用面和字段 shape，用于恢复/审计；Catalog 非数据树 receiver 无条件信任且不以 continuation 做授权判断；system 调用不发送 delegated header |
| App Shell Current Principal bootstrap | `implemented` | `workspacemember/user_info.go`, Frontend principal context store/request client | user info projection、BusinessContextProvider tests | Role context 非 ready 不扩展 capability |
| `admin`/`superadmin` Core PDP 路径 | `implemented` | `iamcore/administrator.go`, `authorizer.go`, `resource_access_filter.go`, `owner_access_plan.go`, `batch_resource_action_projection.go`, `principal_access_projection.go`；workspace bootstrap 的 `database_role.go` | `superadmin_test.go`, `resource_access_filter_test.go`, `owner_access_plan_test.go`, `batch_resource_action_projection_test.go`, `principal_access_projection_test.go`, Backend decision tests, workspace bootstrap/readback tests | 当前 Effective Role 的 direct binding、真实性与 lifecycle 验证后立即快通；不读取 Registry、Policy、Role Graph、target Ownership、资源层级、DCL 或业务元数据。point 直接 allow，collection 返回 `AllResources`，owner projection 全部 `uniform_allow`；MatrixOne 侧仍依赖初始化时物化的完整产品数据库/表权限 |
| Role 创建/编辑、Policy/Graph/Binding/Default Role | `implemented` | native `service/iam/role_provisioning.go`、`role_update.go` 与 tenant IAM Repository；成员绑定走 canonical workspace API | Role 创建失败清理；PATCH 本地原子回滚、三版本 CAS、成功回执、跨 MO 中断与有限收尾回归；Product SDK 定向用例已补充 | 本地未发布；PATCH 已移除旧快照补偿与子操作恢复，失败保留 Role 占用。完整集成验证交由 CI，合同见[生命周期 §4.3](04-storage-lifecycle-audit.md#43-role-创建与编辑) |
| Role 删除 | `implemented` | native `service/iam/role_administration.go`、`role_delete_recovery.go`、`role_delete_ownership.go`、tenant `iam_role_delete.go` / `iam_role_delete_ownership.go`、生成权限边界及 Mowl 恢复装配 | 既有原子清理、成功回执、Saga 持久预算、原身份重验和失败终态定向测试已通过；本轮新增完整转移、版本冲突、目标拒绝、回滚、自动重试重验、前端三种模式及 SDK 用例，双认证 Product SDK 转移场景已补充 | 有对象时要求完整转移；同请求冻结目标和版本，接收角色 Ownership 保留。Saga 继续作为唯一执行状态源，Role 行锁覆盖外部副作用及本地事务；本轮真实完整集成环境未运行，全链路仍待 CI。详见[生命周期合同 §4.2](04-storage-lifecycle-audit.md#42-role-删除) |
| Ownership/Object Grant/Role lifecycle | `contract-gap` | `iamcore/ownership_*`, `resource_lifecycle.go`, `role_graph.go`, `mutation_guard.go`, `object_grants_service.go`, `database_registration.go`；tenant `iam_ownership.go`, `iam_role_mutation.go` | ownership/lifecycle/grant、direct/inherited Owner delegation、non-owner WGO、Role delete impact tests | 本行其它差距沿用旧基线：active Direct/inherited Owner 可授予同一 exact 对象的普通 grantable action；但 `IAMObjectGrantsService.ApplyObjectGrants` 目前仍在判断 workspace `role.create` 或 `role.update` 前无条件调用 `validateObjectGrantOwnership`。Database delete 已允许 exact-key 缺失，但 non-active/畸形 Ownership 仍终止业务删除。这些业务访问与管理路径不能以 Ownership 为额外 gate。当前 Role 删除的完整转移要求见上一行；旧 `ownership-impact` 的 `can_delete=false` 仅为观测字段，不再用于删除预检 |
| Role 启用/禁用 | `implemented` | Backend `handlers/iam`、`iampep`；Core `iamcore/role_lifecycle_mutation.go`、tenant `iam_role_lifecycle.go` | lifecycle 归属保留、BFF 单次 PDP、冻结身份、CAS/幂等、审计回滚、双语错误与日志测试；真实存储覆盖由 CI 执行 | 禁用/启用不查询或阻塞于 Ownership；BFF 完成产品准入，非数据树 Core 消费可信执行身份且不重复 PDP；事务内保留 actor binding/lifecycle 与目标版本校验。审计显示复用请求内成员显示快照，不复用授权决定 |
| 业务对象与 Ownership 一致完成（MOI） | `implemented` | `moi/pkg/service/iam/platform/resource_mutation.go`；`moi/pkg/service/{runner,sandbox,workflow,exporttask,dashboard}` 原持久操作；Catalog Table 共享元数据事务 | `TestResourceMutationRejectsAfterCommitBeforeBusinessMutation`、`TestOwnershipCompilerRejectsAfterCommitCreation`、`TestRunnerOwnershipFailureKeepsOriginalIntentRecoverable`、`TestSandboxOwnershipFailureRetainsOriginalReservation`、`TestWorkflowDeleteOwnershipFailureRetainsOriginalCommand`、`TestDashboardOwnershipFailureKeepsDeletionRecoverable`、`TestDeleteTableMetadataJoinsOwnershipTransaction` | 本地工作树未发布；真实 MatrixOne 集成验证尚未执行。历史持久操作若缺少完整冻结身份，执行必须返回错误并保留原记录，不能推测创建者/删除者或写成功终态。历史缺失 Ownership 的授权与补录另遵循 §3.4，不把普通缺失当作全局 deny |
| canonical member/profile/tag/audit | `implemented` | `iamcore/workspace_members.go`, `workspace_member_audit.go`, `role_bindings.go`, tenant subject attributes；Backend 成员/tag 入口按独立 action 准入，可信 Core 内部定位、角色绑定与审计查询不重复业务 PDP；Backend IAM shared actor display projector 与 Frontend member audit DTO/UI | workspace member/binding/audit handler/service tests、Frontend member/tag hooks 与弹窗测试 | Frontend 消费 shell 的唯一 IAM 上下文，按 workspace、Effective Role、epoch 隔离查询缓存；安全公开错误、响应契约异常、网络失败与合法空集合分别处理。actor 展示名解析失败时仍显示占位文案 |
| 邀请接受 Saga 与显式重试 | `implemented` | `moi/pkg/service/workspace/invitation_accept.go`；`moi/pkg/service/workspacemember/mutation.go`；`moi/pkg/dao/system/workspace_invitation_acceptance.go` | `TestWorkspaceInvitationFinalizationRetryThroughProductSDK` 覆盖真实 system 提交故障、有限重试及受邀者再次接受；`TestWorkspaceAcceptingInvitationThroughProductSDK`、自动接受和重新邀请集成场景；`TestInvitationAcceptRetriesOnlyUnfinishedMOIFinalization` 与取消重试单测 | 复用原邀请 ID、成员 ID 和凭据，成功步骤持久化后不重放；每次显式接受有有限重试预算，失败不封锁再次接受，不注册邀请周期恢复。成员在 MO 和全部 MOI 事实完成后才激活；原目标归属、生命周期、角色可分配性、CAS 和审计约束保持。删除后重新邀请使用新 membership ID，旧操作回执与审计独立保留 |
| GitHub 用户名邀请 | `implemented` | native `CreateMember` 与 UC directory | Product SDK GitHub 邀请集成、invitation_accept 与 CreateUserModal 定向测试 | UC 已绑定且可用的账号立即入组；未命中返回 `USER_NOT_FOUND`，不保存挂起记录或登录认领；不查询 GitHub.com |
| 自助 Default Role 首次选择 | `implemented` | Backend `handlers/iam/iam.go` 与 `iampep/request_admission.go`；Core `iamcore/principal_context.go` | selected-target admission/transport、direct binding/lifecycle 与 CAS tests | 无显式候选时将本次显式选择的目标角色交由 Core 首次验证；有显式候选时保留优先级，失败不替换候选。可信写入复用冻结身份并保留目标角色约束 |
| MatrixOne data privilege/Active Role | `implemented` | `iamcore/data_privilege_*`, `matrixone_data_privilege_adapter.go`；`workspace/sql_effective_role_resolver.go`、tenant `iam_subject_attributes.go`、`model/sqlsession` | unit + live capability probe tests；`TestIAMDataPrivilegeExecutionServiceLiveRowColumnEnforcement/subject-attributes` 在本地 MO 4.2.2 验证共享角色不同用户、改值、删除、空值、SQL 字面量和列隐藏 | database/table DCL 与 row/column 分别受 capability gate 控制；2026-09-16 当前工作树补充 `expression` 用户标签引用，签发连接时重新取值；SQL Editor WebSocket 需重新连接；原生直连和长期复用已签发连接资料由调用者管理，不强制更新正在执行的查询 |
| permission model hard removal | `cleanup-gap` | runtime allow 已删除；Offset110 reset 已落地；成员 Role 兼容入口 clean-break 已完成 | Offset110 fixture/latest-upgrade gate、canonical IAM boundary gates、SDK/route deletion checks | 其余 legacy 物理资产与真实环境验收见 [M8 计划](plans/m8-legacy-hard-removal.md) |

## 3. 产品资源接入

本节的 `implemented` 只表示该资源的 Registry、PEP/PDP 与主要业务授权已接入；正常创建/删除的一致性要求以第 2 节 MOI 增量和[生命周期合同 §3.3](04-storage-lifecycle-audit.md#33-ownership-登记与清理)为准。历史基线中的后置单次登记、失败仅记录日志等行为不再是目标合同，也不能作为新接线的放行依据。

| 资源域 | Status | Production evidence | Test/gate evidence | Known limitation |
| --- | --- | --- | --- | --- |
| Workspace Member / Role | `implemented` | IAM Core management services；`moi-backend/pkg/handlers/iam/iam.go` canonical user Role binding handlers；`moi-backend/pkg/handlers/workspacemember` 仅保留成员资料/生命周期能力 | member/role/default/audit tests；`moi-backend/cmd/sdk-route-manifest`、Go/Python IAM SDK route-alignment 与 typed binding tests | 成员 Role 更新已完成 clean-break；其余历史权限物理资产与真实环境验收仍由 M8 2.2/2.3 跟踪 |
| Connector | `implemented` | Backend connector PEP、Registry、业务生命周期查询与创建/删除恢复；`moi-backend/pkg/dataconn/connector_impl.go` | connector_create_iam、connector_delete_iam、connector_visibility、registration/route tests | 旧基线的业务提交后单次登记/清理方式不满足当前一致性合同；本行只证明原 Registry 与业务授权接入，不能证明生命周期已按新合同完成。MOI 普通对象通过生成 mutation 的同一 tenant transaction 完成业务、Ownership 与审计，故障必须整体回滚；运行时身份和实际数据边界仍独立裁决 |
| Workflow | `implemented` | Backend route PEP、Registry、Core ownership；BFF/Core 入口完成 `workflow.run` 后，Worker 通过专用 sender 创建 child Task | canonical route/registration、embedded/proxy workflow trigger tests | Catalog Task 是非数据树 receiver，不重复解析或授权 child Workflow；动态服务入口见例外登记 |
| Compute Resource | `implemented` | Catalog List/Get `OwnerAccessPlan`、Core query validation、all/specific/empty SQL query shape、conditional `allowed_actions` projection 与 final fence | `owner_access_plan_test.go`, `batch_resource_action_projection_test.go`, `compute_resource_test.go`, tenant `iam_ownership_test.go` | canonical `compute_resource.read.all` 或 system all-access 使用普通 owner SQL；显式 exact specific read 不逐对象回查 Ownership，Owner 派生 ID 保持 strict Ownership batch；当前 bounded projection 不登记 parent/path shape；每个 action 独立决定 uniform/candidate，mutation 仍重新 point Authorize |
| Data Dashboard | `implemented` | Backend route PEP、Catalog Ownership 与 collection filter；可信 BFF 和内部调用的 `execution-spec`/`evaluate-alert` 直接进入 | Dashboard handler/route、BFF facts 审计、Worker sender metadata 与 batch filter tests | `data_dashboard.use` 不授予 SQL 数据权限；Dashboard list 保留已确认的 `ResourceAccessFilter` 过渡例外，source Table 和 MatrixOne 仍按各自数据边界校验 |
| API Service | `implemented` | 独立 Registry/resource、稳定 WorkflowApp 映射、Catalog ownership，以及 `api_service.run` 与显式 Compute Resource 的运行期二次授权 | API Service publish/runtime/readiness tests、route checker | 空 `compute_resource_id` 是未绑定默认执行路径，不产生具体 Compute Resource action；普通 Workflow Dynamic Service 仍遵循例外登记 |
| Catalog / Database / Volume / Table | `implemented` | Registry、resource picker、data privilege adapters；逻辑 Catalog 数据树及暴露已挂载 File/Volume 的 bridge 在 payload 读写前解析 canonical root 并执行独立 PDP | canonical registry、picker、data privilege、file/root-Volume point authorization tests | Table 已接入；Data Asset manifest/lineage/state 仅为可信 transport，实际 File/Volume mapping 仍执行 `volume.read`；Data Privilege 不能按单一 ready 状态理解 |
| Model Backend / Model Router | `implemented` | Registry、LLM/embedding/parser list filter、内部 Model Gateway router、External Catalog 成员/Effective Role 重验 | model backend registration、route checker、external catalog Role verification、role create initial-policy tests | Backend 对象仅覆盖 BFF 控制面 CRUD/list；独立 Runner/Sandbox CLI 是 transport capability，不定义 `model_backend.use` 或模型运行时 Role 权限；历史 policy 中的旧 runtime grant 不再参与授权 |
| Agent 产品对象 | `implemented` | Agent CRUD/list/use PEP、Core Agent handler、task-scoped RuntimeGrant | registry、runtime/gateway tests | A2A 创建任务时执行一次 `agent.use`；Gateway 不做 live PEP |
| Agent Sandbox / Runner | `implemented` | Backend A2A admission PEP；Catalog task/executor RuntimeGrant binding 与 dispatch authorization gateway；Astra `edge_ws_authorized` live-send PEP | Backend edge-use、Catalog executor gateway/Core unavailable/revocation、Astra descriptor 与 no-dispatch-on-revocation tests | `eph-*` 保持 conversation-bound；Matrixflow 与支持版本化 transport 的 Astra 需按发布顺序部署，旧 Astra fail closed |
| Workbook | `implemented` | SQL Editor PEP、Registry、role-bound connection | registry、workbook/verified-role connection tests | SQL 前必须动态重验 Role |
| Web Search | `parent-feature-admission` | native 搜索执行由 Agent/Automation 父功能准入；通用 Channel resolver 校验 workspace、Tool/provider 与凭据生命周期；整组独立权限已退役，存量授权不参与决策 | Channel resolver 定向回归；Product SDK 普通成员搜索场景由 CI 验证 | 配置入口当前为有效 workspace Role 准入，后续独立设计配置管理权限与命名 |
| Agent Team / IngressConnection | `in-progress` | 显式 Team 领域模型、独立 IngressConnection、Agent/Team TargetRef 关联 CAS、两类 Session owner 的持久 admission、Managed Receiver、Tenant SQL store、Team Runtime Session / Astra 映射、收件与 Runtime 原子交接、canonical Registry | agentteam/channelingress/agentruntime/schema/registry tests | 仍待全平台两类目标 E2E、完整故障矩阵与前端连接教程验收；既有 callbackrouting automation 不参与对话 dispatch |
| Data Publish / Subscription | `implemented` | native `moi/pkg/service/datashare`、两张 system 产品身份表、MO fact adapter、生成权限边界及 IAM owner | global mutation/recovery、Ownership、路由和订阅重启测试 | 本行表示主要资源与授权已接入；统一 Saga 合同仍为 `contract-gap`，具体差距见下节。workspace/account 删除按独立合同处理，不作为发布订阅 Saga 已完成的证据；旧租户兼容表仍保留 |
| Data Task | `runtime-gap` | CRUD/list 与 DB import role context 已接入 | Registry/route/DB import tests | 其它异步依赖仍需 M6 全覆盖 |
| Export Task | `runtime-gap` | admission、CRUD/list、Ownership 已接入 | Registry/route tests | worker 源文件/外部目标动态重验未全闭环 |
| Semantic Model | `runtime-gap` | CRUD/use admission 与 Ownership 已接入 | Registry/registration tests | re-embedding/source reconcile 的所有依赖未全闭环 |
| Custom Operator | `implemented` | Registry、Workflow node routes、lifecycle | registration tests | 仅 Custom Operator source 以 `custom_operator.use` 参与 API Service 发布；内置 WorkItem 不因此成为对象资源 |

### Data Share Saga 统一合同差距

2026-11-07 更新接受订阅（含重新订阅）、取消订阅及其重启恢复的实现增量。所有发布订阅操作仍以
[Runbook §0.8](../data-share/moi-data-share-global-cutover.md#08-生命周期)为唯一生命周期合同；发布创建、修改和删除的
剩余差距单独保留，不能把订阅路径已完成视为全操作验收。下表只更新 Data Share，其余历史基线保持原说明。

| 范围 | 当前证据与差距 |
| --- | --- |
| 正常执行重试 | [`executeMutationDDL` / `executeMutationLocal`](../../moi/pkg/service/datashare/mutation_command.go) 使用原 Saga `StepState` 持久化已用预算。订阅的准备、Catalog/IAM、全局激活及取消清理均已接入，正常执行和恢复不会重开预算；已确认的 MO 副作用不重复执行。发布操作其余业务阶段仍需逐项核对。 |
| Failed 与锁释放 | [`failGlobalMutation` / `finishGlobalMutationStatus`](../../moi/pkg/service/datashare/global_snapshot.go) 将发布及订阅失败终态与本任务锁释放原子提交，保留半成品及原失败结果。必要补偿不再先发布 Failed 再复活；终态事务故障保存提交意图，恢复只补提交，未提交时不伪报解锁。补偿预算耗尽同样进入 Failed 并释放本任务锁。 |
| 崩溃与未决 DDL | [`recoverGlobalSubscription`](../../moi/pkg/service/datashare/global_runtime_recovery.go) 确认已建库后只补必要事实，未建库则终结原接受；未决、查询和清理失败消耗剩余预算，耗尽后 Failed/解锁。取消订阅先确认删除结果，再做必要清理。复用库不会变成本任务新建的副作用；系统核验不重开订阅预算或复活 Failed。发布操作同样通过统一入口读回外部步骤；未开始业务的旧修改/删除意图终结并解锁，保留现有资源。 |
| 新 Saga 接续 | [`failedSubscriptionForNewSaga`](../../moi/pkg/service/datashare/global_subscription_retry.go) 已覆盖接受失败后重新订阅或直接取消、取消失败后重新订阅。新 Saga 加锁后按当前事实与本次意图处理，保留匹配的完整 Ownership；旧删除仅准入或只读校验时结束旧意图并保留原库；[持久回执查询](../../moi/pkg/dao/system/data_share.go)与锁占用分离，列表不因解锁将半成品误报为已订阅。重新发布、修改及其跨操作接续仍待补齐。 |
| 特殊异常诊断 | [`mutation_logging.go`](../../moi/pkg/service/datashare/mutation_logging.go) 已记录中断阶段、DDL 结论、执行器/fence、原请求与资源身份及原始错误，并有诊断与晚到执行回归；日志不替代有限重试、业务收尾或终态解锁。 |
| 验收范围 | 已补接受/取消的双认证 Product SDK 失败接续与真实重启场景，覆盖剩余预算、终态解锁和旧失败回执不变；定向包测试另覆盖未知结果、身份冲突、清理故障、终态提交故障及晚到回调。发布操作仍须按 §0.13 补完整矩阵；历史投影 cutover 与 workspace/account 删除继续独立验证。 |

## 4. 明确的 membership-only / transport-only

以下状态不产生业务 action allow，完整边界见[业务权限模型例外登记](10-business-permission-model-exceptions.md)：

| 能力 | Status | Guard | 边界 |
| --- | --- | --- | --- |
| WorkItem Catalog list/detail | `transition-membership-only` | Backend `RequireVerifiedEffectiveRole` + Core verified-role guard | 只读节点能力元数据 |
| Workflow Template | `transition-membership-only` | 有效 workspace membership + workspace/reserved-admin 写约束 | 内置模板只读；自定义模板只在当前 workspace 可见 |
| Workflow Lineage 未完成父资源解析的 read/revision | `transition-membership-only` | 有效 workspace membership | 已解析父 Workflow 的 rerun 已使用 `workflow.run` |
| 临时候选文件 upload/download/stream/delete | `transition-membership-only` | verified-role transport | 不是 canonical Volume；Core 错误保持非 2xx |
| 未挂载 Volume 文件的统一成员访问 | `transition-membership-only` | Core `volume.RequestAuthorization.Prepare`、`workspacefileupload.AccessChecker` 与 Data Asset 文件产物桥接门禁共用 tenant 文件存在性与挂载分类，复用请求中 Core 已验证的成员身份 | 未挂载文件不生成 `volume.*` allow；文件 owner 读取当前挂载关系，挂载后切换为 canonical Root/action。定向测试覆盖批量、身份绑定、异常拒绝与管理员零准备读取；真实 Backend → Core → MatrixOne 回归由 `issue_14039_file_containment_integration_test.go` 覆盖，待 CI 验证 |
| Data Asset 内部 manifest/lineage/state | `transport-only` | 可信 BFF/内部 transport + workspace tenant transaction | 不注册 `data_asset.*` action；不要求 execution contract；关联实际 File/Volume 的 mapping alias 仍执行 `volume.read` |
| A2A task/manifest/feedback transport | `transition-membership-only` | verified-role transport | 解析真实 Agent 后必须 `agent.use` |
| LLM session/message/tag transport | `transition-membership-only` | verified-role transport | 当前不是独立 canonical resource |
| Data Share workspace-name projection | `transition-membership-only` | verified-role transport | 只返回已有 publish/subscription 关系可见名称 |
| Compute Resource Spec | `platform-capability` | list: 有效 membership；mutation: Core `spec_admin.accounts` | 不注册 workspace IAM resource/action |
| Alerting Rule/Receiver/History | `transition-membership-only` | 有效 workspace membership | 正式资源模型仍是 `blocked-unsupported` |
| Apps/HR Screening | `transition-membership-only` | 有效 workspace membership | POC 尚未产品化 |
| 普通 Workflow Dynamic Service | `transition-membership-only` | 有效 workspace membership | 待可信 Workflow resolver 后迁入 `workflow.run` |
| Skill metadata/version management | `transition-membership-only` | Backend Verified Effective Role + Core verified-role guard | 仅当前 workspace；待冻结 Skill Ownership、resource/action 与可信 resolver 后接入对象授权 |
| Channel Instance 配置 | `transition-membership-only` | native generated boundary 的有效 workspace Role 准入 | 包含 Web Search、GitHub/WeCom 等；IngressConnection 使用独立对象 PEP。Web Search 内部执行沿父功能准入 |

## 5. 未完成与不支持

| 能力 | Status | Evidence | 当前行为 |
| --- | --- | --- | --- |
| 未经 Gateway 的 chat/embedding/parser runtime 全依赖重验 | `runtime-gap` | 资源目录旧差距与当前 route/runtime 代码 | 由 M6 按实际资源逐条收口 |
| Alerting 对象权限产品化 | `blocked-unsupported` | 无 canonical Registry resource/action | 当前 membership-only 不复用其它资源 action |
| HR Screening/Apps POC 产品化 | `poc-not-productized` | 无 canonical Registry resource/action | 当前 membership-only 不能扩散为通用 allow |
| 普通 Workflow Dynamic Service 对象授权 | `blocked-unsupported` | 缺可信 workflow resolver/运行合同 | 当前 membership-only；不能伪造 `workflow.run` |
| 历史 canonical 对象 Ownership cutover | `contract-gap` | Catalog/Volume best-effort startup backfill 与 tenant storage；Data Share `service/datashare/cutover.go` / `migration.go`；Compute Resource 显式 adoption/受保护 lifecycle mutation；真实 MatrixOne exact-key 查询与锁顺序回归 | Root Volume 与 Catalog 已按 workspace 单轮幂等补录：只选择 exact-key Ownership 完全不存在的对象并登记默认 `superadmin`，失败记录结构化上下文和原始错误后继续启动，本进程不重试且下次启动重查，不安装授权 gate、不改变 readiness。Data Share `finalize` 当前仍先执行 `repairOwnershipAndRescanDataShareMigration`，repair 失败会阻止 `global_paused -> global`，尚未满足“Ownership 补录不影响功能”的统一合同；需要拆成关系 cutover 与 best-effort Ownership 补录。multi-replica 专项验收仍待补充 |
| PermissionService/direct binding/system-role shortcut | `retired` | canonical boundary tests、Offset110 | 禁止恢复 |
| legacy 物理资产与兼容入口清理 | `cleanup-gap` | 成员 Role 兼容入口、旧 DTO、route matrix 和 SDK/CLI surface 已删除；其余历史权限物理资产见 M8 清单 | 按 [M8 计划](plans/m8-legacy-hard-removal.md) 的 2.2/2.3 完成后才能关闭 |

## 6. 更新规则

更新任何状态行必须同时给出：

1. 生产代码路径；
2. 能证明 allow、deny、inactive、Core unavailable、workspace/Role mismatch 的测试或 gate；
3. 对资源索引、例外登记和 M6/M8 计划的同步修改；
4. 包含对应生产行为的 `verified_against_commit`。

“route 已挂 middleware”“Registry 已有 action”或“测试 mock 返回 allow”都不能单独把状态改为 `implemented`。
