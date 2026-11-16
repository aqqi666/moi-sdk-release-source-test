# MOI 业务功能权限模型目录

> 最后更新时间：2026-09-01

本文是 MOI 当前业务功能接入 IAM 的规范性查阅目录，也是新增业务功能设计权限合同的必读输入。它回答以下问题：

- 一个业务功能使用哪个 canonical resource/action；
- action 授权当前 workspace、父容器还是具体对象；
- list/search/picker 如何在分页前过滤；
- create/delete 如何维护 Ownership 和 lifecycle；
- 从属对象与运行期依赖复用哪个父资源 action；
- 哪些接口当前明确属于 platform、membership-only、transport-only 或未支持边界。

本文不保存运行期 allow，也不替代代码事实源。精确 action/resource 集合以 Core Registry 和它的[派生快照](09-business-permission-model-registry.md)为准；精确 Backend route 清单和当前接入状态分别以生成的 [route authorization inventory](../../moi-backend/docs/rbac-route-matrix.md) 与 [实现状态](05-implementation-status.md) 为准。发现三者不一致时，先判断产品模型冲突、实现缺陷或文档漂移，不能直接选择较宽松的一项。

## 1. 查阅与维护规则

权限接入或修改按以下顺序使用本文：

1. 在本文找到目标业务功能，确认 resource、action、授权层级、可信 ID/parent 和依赖资源。
2. 涉及请求/运行期、生命周期或公开契约时，分别追加阅读 [请求与运行期合同](03-request-runtime-contracts.md)、[存储、生命周期与审计](04-storage-lifecycle-audit.md)或[公开 API、前端与 SDK 合同](07-public-api-frontend-sdk-contracts.md)。
3. 在 Core Registry 核对 operation requirement 和 route binding；不得从 Backend 旧权限码反推 action。
4. 按 [接入指南](integration-guide.md) 实现 PEP/PDP、集合过滤、Ownership，以及 Mowl 内部延续与外部受保护服务重新鉴权边界。
5. 按 [验证与漂移控制](06-verification-drift-control.md) 更新测试、route checker、派生索引和实现状态。

新增或改变 resource/action、授权层级、Policy scope、Ownership 或公开 API 前，必须先列出影响和方案并获得确认。只修复代码与本文既定合同的偏差时，不得借机扩大 action 语义。

## 2. 通用授权层级

| 授权层级 | Authorize resource | Policy scope | 适用场景 |
| --- | --- | --- | --- |
| workspace | `workspace/<workspace_id>` | `all`（本目录的 workspace action 只允许 all） | workspace 级目录创建和目录集合展示 |
| parent object | `<parent_type>/<parent_id>` | Catalog 数据树创建按指定父容器授权；父容器内不再指定尚未创建的子对象 | 在明确父容器下创建子资源 |
| object | `<resource_type>/<resource_id>` | 普通应用对象查看只允许 `all`；Database/Volume/Table 查看支持指定对象；其它操作按 action 定义 | 对已有对象执行对应操作 |
| collection | 同类对象的 Core filter | 复用对象 read/use action | list/search/picker，在 count、排序和 pagination 前过滤 |
| platform | 平台账号或平台管理员事实 | 不进入 workspace Application Policy | workspace 创建/删除、`spec_admin.accounts` 等平台接口 |
| membership-only | 当前 workspace 的 Verified Effective Role | 不产生业务 action allow | 仅限[业务权限模型例外登记](10-business-permission-model-exceptions.md)明确列出的能力 |

Catalog 的当前持久化与前端树为 `workspace -> catalog -> database -> volume/table`。创建动作授权真实父 scope：Database 的父 scope 是 Catalog，Volume 和 Table 的父 scope 均为 Database。父 scope 内的创建能力不选择尚未存在的子对象。`workspace.create_catalog` 和 `workspace.show_catalogs` 在 Workspace 上仍只接受 `all`；Catalog 自身的查看是 workspace 全局能力，Database、Volume、Table 的查看则支持指定对象。目录浏览不能替代敏感子对象的查看授权；点查与列表过滤必须使用相同对象 action。

对象级 action 的 `all` 表示当前 workspace 内同 resource type 的全部 canonical active 对象；specific 只表示明确稳定 ID。普通 Role 的数据面 action 还必须满足对应 MatrixOne DCL；`admin`/`superadmin` 使用 workspace bootstrap 已物化的完整 MO Role 权限。两者都不能绕过 resource resolver、workspace/lifecycle 或 protected target，也不以 target Ownership 为额外 allow 条件。parent/path grant 同样由 canonical 业务层级匹配。只有 Owner 派生权限要求 active Ownership。

canonical active Ownership 等价于同一 exact 对象全部可授权 Application IAM 操作及其对应 grant/revoke 能力的集合。Direct Owner 和通过 active 普通 Role graph 继承到的 Owner 权限相同，继承边 WGO 不削减该集合。对于 MatrixOne 数据对象，Owner 还可通过 Data Privilege 接口按 WGO 语义委派该 exact 对象；这项委派能力不产生 `role.create` 或 `role.update`，也不让 MOI Ownership 绕过实际 DDL/DML 所需的 MatrixOne DCL。

普通应用对象的创建和查看只有当前 workspace 内的“无权限 / `all`”两种可配置状态，当前 workspace 本身的 exact scope 也表示同一 workspace 的全局能力。Catalog 数据树有父 scope 和敏感数据例外：Database、Volume、Table 的查看支持指定对象；创建是获准父容器内创建该类子对象的能力，不需要也不能选择尚不存在的子对象。父容器范围必须由可信资源关系解析，不得按客户端传入的名称或 ID 推断。Database 创建以 Catalog 为父 scope，Volume 和 Table 创建以 Database 为父 scope；Table 的建表、查询和行列规则对齐 MatrixOne。使用、执行、修改、删除继续使用各自已登记范围。Ownership 的同对象正向权限不变；只有全局创建/查看的普通应用对象不允许据此向其他 Role 转授 exact 创建/查看权限。

所有对象 list/search/picker 均复用 read 或明确的 use action，不注册 `*.list`。Core `ResourceAccessFilter` 必须在 total 和 pagination 前执行；空 ID 集合返回空页，不能退化为查全部。

## 3. Workspace、成员与 Role

### 3.1 Workspace 与平台账号

workspace 是 tenant IAM 隔离边界，不是普通 Role 可按对象配置的业务资源。

会话内的 CLI 与 MCP 可使用合法 active-task 身份进入同一工作区产品接口；按[请求与运行期合同](03-request-runtime-contracts.md)恢复冻结 Role，继续执行本目录对应业务的当前授权。传输形式不产生额外权限，也不能将任务请求改为默认 Role 请求。

| 业务功能                     | 权限合同                                                                                                                                                 |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 创建 workspace               | 已认证账号的平台能力；成功后创建唯一 owner `superadmin` binding、Default Role、workspace Ownership 和 IAM seed                                           |
| 我的 workspace 列表/基础信息 | 账号与 workspace membership/owner 关系；不读取当前 workspace Application Policy                                                                          |
| 更新 workspace               | 仅唯一创建者的平台账号管理能力；不能通过 `admin`、`superadmin` Effective Role 或普通 workspace Role grant 获得                                           |
| 删除 workspace               | 仅唯一创建者的平台账号管理能力；不能通过 `admin`、`superadmin` Effective Role 或普通 workspace Role grant 获得，且仍执行 lifecycle、引用、审计和幂等校验 |
| 触发 workspace 垃圾回收      | BFF 只消费 Core 已验证的 `is_workspace_owner` 事实；不注册 IAM resource/action，不调用通用业务 PDP；`coreclient` 普通转发后 Catalog 无条件信任           |
| `/admin/compute-resources`   | `spec_admin.accounts` 平台管理员能力；workspace owner/superadmin 不自动获得                                                                              |

工作区列表展示当前 canonical 用户在正常工作区收到的 `pending` 和 `accepting` 邀请，均沿用 `access_status=pending` 与 `invitation_id` 投影。CLI `POST /newmoi/auth/cli/bootstrap` 同样保留邀请 ID，并返回 `status=PENDING_INVITATION`，使客户端能够直接使用 bootstrap 响应重试接受。接受中断或有限重试耗尽后邀请仍可见，受邀者通过既有接受接口继续原邀请的未完成 Saga 步骤，不需要等待周期性恢复或重新创建邀请；已确认完成的 MatrixOne 步骤不会因 MOI 提交失败而重复执行。列表展示不创建 membership 或提前授予资源访问权限。接受完成后按既有已加入工作区投影返回，已取消或已接受的邀请不再作为邀请条目展示。

首页概览的任务执行状态统计不设独立 action；只允许当前 workspace 的有效成员及已验证 Effective Role 读取聚合投影，不授予任务详情、运行或管理权限。

当前主体 `/iam/me/capabilities` 沿用同一身份、membership 与 Effective Role 校验，按生成的 capability manifest 投影权限。可通过重复的 `capability_id` 参数只计算支持的请求项，未登记的 ID 在成功响应的 `unsupported_capability_ids` 中返回，不新增 resource/action 或业务专用权限入口；输入与响应合同见[按 ID 查询当前主体 Capability](07-public-api-frontend-sdk-contracts.md#21-按-id-查询当前主体-capability)。

### 3.2 Workspace 治理 Action

以下 action 全部授权当前 `workspace/<workspace_id>`，不登记对象 Ownership。

| Action | 业务功能/API 分类 | 关键边界 |
| --- | --- | --- |
| `query_history.read` | SQL history overview/list/detail/profile；“我的历史 / 工作区历史”是查询分类 | 两类查询统一授权并使用当前 principal 与 Verified Effective Role 对应的 MatrixOne user；self 追加当前用户过滤，workspace 可查询同一 account 内其他用户历史。授予或撤销时同步物化 MO Role 对 `system.statement_info` 的 SELECT，不区分本人和其他成员的权限 |
| `model_router.read` | LLM/Embedding/Parser router GET | 只读取 workspace 路由配置，不代表 Backend 可见或可用 |
| `model_router.update` | LLM/Embedding/Parser router PUT | 只修改 workspace 路由策略；Backend/endpoint 仍独立校验 |
| `resource.ownership.repair` | 修复缺失或漂移的 Ownership | 可沿有效 Role graph 继承；仍是受保护的修复边界，不是普通对象 allow |

已有对象的 Owner Role 转移由对象 Owner 或具有 workspace `role.update` 的当前 Verified Effective Role 操作，不注册独立 action。Owner 匹配、目标 Role 校验、版本 CAS 与审计遵循[Ownership 合同](04-storage-lifecycle-audit.md#33-ownership-登记与清理)；普通对象授权不会获得该管理能力。

### 3.3 Workspace Member

Member 的 canonical identity 是 `(workspace_id, moi_user_id)`。全部 action 都是 workspace 级治理权限，不支持逐成员 scope，也不为 Member 登记 Direct Ownership。

成员删除完成后，再次邀请同一用户创建新的 membership ID，不复用已删除关系的 ID 或生命周期版本。已删除关系不构成新邀请的成员冲突；旧请求的回执与审计按原 membership ID 保留，重放旧删除请求不能影响新成员关系。同一邀请的接受重试仍沿用该邀请已持久化的 membership ID。

成员列表与标签定义列表按 `workspace_member.read` 决定可见范围：当前有效 Role 有权时返回工作区内的集合，无权时返回 `200`、空数组和 `total: 0`，且不查询成员、待邀请成员或标签数据。成员详情和写操作仍保留正常的权限拒绝；身份、membership、Role lifecycle 或必要依赖异常不能转换为空列表。

成员删除先持久化删除意图，保留 System membership 与数据库账号映射；系统删除收尾提交前，成员继续保持原来的 `active`/`disabled` 状态。删除顺序为 MatrixOne 用户账号、tenant 角色绑定/默认角色/资料、System 成员关系；tenant 清理失败仍尝试最后的 System 删除并保留失败回执，System 收尾失败不回退已完成的 tenant 清理；删除开始的审计在 MO 清理前写入。成员管理列表以 `deletion_incomplete` 保留当前未完成删除记录；有权操作者可通过原删除接口显式继续同一请求，继续前重新验证权限、原成员身份和版本。账号清理失败时记录仍按原成员状态可访问；System 收尾成功但 tenant 清理失败时成员已不能访问，移除成员接口返回成功并从列表隐藏；残留 tenant 事实、失败回执与详细错误日志保留给运维处理，不提供用户继续删除入口。新邀请仍需先完成旧绑定清理，避免继承残留权限。列表读取不执行重试；重启恢复只接续中断的未结束操作，最终失败等待用户显式处理，不改变角色删除检查。

成员资料、启停和删除分别只要求对应的工作区 action，不额外要求 `workspace_member.read`。Backend 在公开入口完成业务 PEP；可信内部调用定位 canonical Member 时复用同一 Verified Effective Role，Core 保留 workspace、受保护目标、业务 lifecycle 与 CAS 校验。持有写权限不会扩大成员列表或详情的读取范围。

| Action                                      | 业务功能/API 分类                                                      | 关键边界                                                                                                                                                                                                                                                                                           |
| ------------------------------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `workspace_member.read`                     | 成员 list/detail、Role binding view、subject-attribute definition list | 返回当前 workspace 的 canonical Member/Invitation 投影                                                                                                                                                                                                                                             |
| `workspace_member.invite` | `/newmoi/user/create` 等邀请入口 | 邮箱、已验证手机号、GitHub login 都必须先匹配 UC 已存在且可用的账号，再解析为 `moi_user_id`；未命中返回 `USER_NOT_FOUND`。三种方式都要求至少一个 assigned Role 和显式 Default Role；邀请及初始角色分配只要求 invite。GitHub 命中立即入组，复用邀请接受流程 |
| `workspace_member.update`                   | alias、description、成员标签值等 profile 修改                          | 目标必须是当前 workspace 的 canonical Member                                                                                                                                                                                                                                                       |
| `workspace_member.subject_attribute.manage` | tag definition create/update/delete                                    | tag 是 subject attribute，不是 Catalog 资源或 allow 事实                                                                                                                                                                                                                                           |
| `workspace_member.role_binding.mutate`      | assigned Role 与 Default Role CAS                                      | 不按数组第一项推断 Default Role；目标 Role 必须 active 且可分配                                                                                                                                                                                                                                    |
| `workspace_member.lifecycle.mutate`         | 普通成员 enable/disable                                                | owner/superadmin 保护独立校验                                                                                                                                                                                                                                                                      |
| `workspace_member.delete`                   | 移除普通成员                                                           | durable cleanup 撤销 MatrixOne user/grant、binding、Default Role 和 profile                                                                                                                                                                                                                        |
| `workspace_member.audit.read`               | 成员 IAM audit                                                         | 只读 Core `iam_audit_events`                                                                                                                                                                                                                                                                       |

邀请 accept/claim 使用 invitation credential 与状态协议，不要求受邀者持有 workspace IAM action。pending invitation 不是 active Member handle。GitHub 立即入座复用同一接受 Saga，不冒充被邀请人 Accept，不平行 AddMember。

定向邀请不保存 UC 未知身份的挂起记录，不因后续注册、绑定或登录自动入组。邮箱和手机号的 pending invitation 也必须关联 UC 已有账号，canonical invitation 仍无 login / uc_sub / 邮箱 / 手机列。只有面向外部用户的链接邀请作为独立渠道可不预先指定 UC 已有账号；本入口不创建链接邀请。

成员或 pending invitation 的产品身份展示投影缺失时，列表不能让整个 workspace 永久返回 `500`。Backend 只能使用 invitation/member 已保存的 canonical ID 与 alias/description 形成明确占位投影，或按已定义状态跳过；不能猜测账号映射、重新激活软删除账号或丢失后续修复所需的稳定 ID。

### 3.4 公共资源标签

公共标签及预定义值是 workspace 共享元数据，稳定 ID 分别为 `resource_tag.id`、`resource_tag_value.id`；不登记独立 Ownership，也不作为 IAM subject attribute 或授权事实。当前 `type=workflow`，赋值指向 `workflow_app.id`，同一资源在同一标签下单选一个值。

| Action | 业务功能/API 分类 | 关键边界 |
| --- | --- | --- |
| `workflow.manage_tag` | `type=workflow` 的标签和值 CRUD、分组、资源查询、赋值回查及赋值入口 | 授权当前 workspace，只配置 `all`；同一个权限覆盖标签定义和值的读写，不要求另一个标签读取权限。删除定义或值同时清除其全部赋值，不要求逐对象修改权限，不删除工作流 |
| `workflow.read` | 按对象列出已赋值标签、标签分组、成员、数量和赋值回查 | 在聚合、未填写判断及分页前应用集合过滤，复用用户列表的 `origin=manual`、来源和业务 lifecycle 范围 |
| `workflow.update` | 批量设置或清除工作流赋值 | 每个目标均须通过正式 Workflow 授权边界和用户工作流范围校验；任一失败整批零写入 |

标签管理权限按资源类型命名，当前仅支持 `workflow`，使用 `workflow.manage_tag`，其授权对象仍是当前 workspace，与 `workflow.create` 相同。创建、集合和赋值请求校验 `type`；已有标签和值的操作根据持久化标签类型校验，未支持的类型拒绝。后续新增类型须登记该类型独立的管理 action，不能沿用工作流权限放行。

定义、可选值与关联写入在 System DB 同事务完成。标签不授予工作流访问权；给具体工作流设置、清除赋值仍要求该对象的 `workflow.update`。工作流删除后残留关联不可见、不计数，随定义、值或 workspace 删除清理。新建、复制和导入工作流不继承赋值。

### 3.5 Role、Policy 与 Role Graph

删除清单的用户、对象总量和阻断原因统一来自删除影响检查；用户与对象列表分别按游标读取当前页，翻页不重新统计总量。转移、解除绑定或显式刷新后更新检查和当前页，最终删除仍校验当前事实。对象分页复用 `role.delete`，用于批量转移的读取同时按请求校验 `role.update`，不把页面保留的总量或版本当作授权。

管理界面的两种“全部转移”按每页 10 条读取对象，逐对象调用独立 Owner 转移接口并提交短事务；中途失败停止后续转移，已成功对象保留接收角色，不回退。只有全部分页处理完成后才单独请求删除角色，不携带 `ownership_transfer`。每次实际转移重新校验 `role.update`、目标角色和对象现有 CAS；结果未知时保留原请求 ID 与参数供显式确认，不新增长期校验标记、集合版本缓存或后台批处理任务。现有 DELETE 携带完整方案的原子合同继续保留。

角色删除仍有 Ownership 时，必须提供完整转移方案，按删除合同原子转移后硬删除；系统角色保护、绑定、默认角色及未完成操作的阻断不变。继承关系不阻止删除，删除弹窗不展示继承提示，删除时清理目标参与的全部继承边，相关角色失去继承权限；其它角色已创建的对象及其 Ownership 保留。转移按当前唯一 Verified Effective Role 同时校验 `role.delete` 和 `role.update`，首次执行、自动重试与重启恢复均重新校验实际转移；没有转移的删除不附加转移权限。接收角色及其 Ownership、业务对象和其它角色的显式授权保留，详见[生命周期合同 §4.2](04-storage-lifecycle-audit.md#42-role-删除)。

Role 的 canonical ID 是 tenant-local Role ID。全部 `role.*` action 授权当前 workspace；目标 Role 只是 mutation invariant，不产生对象级 Role allow，也不登记 Role Ownership。

独立 Application Policy validate/apply 校验整份策略的替换权限。当前 Verified Effective Role 为 `admin` 或 `superadmin`，或具备 workspace `role.create` 或 `role.update` 即可准入。canonical active Ownership 可用于单对象授权与数据权限委派，范围限于其 exact 对象。

具备当前 workspace `role.read` 的管理者可只读预览 active 或 disabled 普通角色的已保存权限。预览返回目标 `lifecycle_state`，disabled 时 `policy_mutation_allowed=false`，界面明确标注停用且不提供编辑入口；该读取不启用角色、不改变策略，也不作为目标角色的实际访问凭据。目标角色作为 Effective Role 时仍必须 active；deleted 角色仍返回不存在，其余不完整或异常事实继续拒绝。


角色数据权限查看沿用 workspace `role.read`：不带 `table_id` 时返回权限与规则摘要，不读取表列结构；传入 canonical `table_id` 时，只返回该角色在该表上的权限和行列配置，并读取一次该表列结构。表必须由当前 workspace 的 Core 资源事实解析，不能接受 SQL 名称或借此读取其它工作区的表；目标角色没有对应权限或规则记录时返回不存在。Frontend 仅在打开单表行列权限弹窗时发起详情请求，列表与对象选择器不能预取全部表列。

| Action | 业务功能/API 分类 | 关键边界 |
| --- | --- | --- |
| `role.read` | Role list/detail、permission view、inheritance graph | workspace 内全量可见；角色列表无权时返回 `200` 和 `roles: []`，详情等点查仍按权限拒绝 |
| `role.audit.read` | Role IAM audit | 目标 Role/workspace/cursor 由 Core 校验 |
| `role.create` | 创建普通 Role 并设置初始权限 | 可沿有效 Role graph 继承；包含本次创建的初始 Application Policy 与 Data Privilege，不叠加其它角色管理权限；Frontend 仅在 IAM context ready、角色导航可见且具备 `role.create` 时开放创建入口 |
| `role.update` | 修改普通 Role 的统一编辑事务 | system Role immutable；一次提交元数据、完整 Application Policy 与 Data Privilege |
| `role.lifecycle.mutate` | enable/disable 普通 Role | disabled 后 policy/Ownership/graph 传播立即失效 |
| `role.delete` | 删除普通 Role | 检查 binding、Default Role、受保护 Role 和未完成业务 operation；继承不阻止删除，删除时清理相关边并保留既有业务对象；仍有 Ownership 时校验完整转移方案；确认 MatrixOne Role 缺失后，同事务完成转移、硬删角色与运行期授权元数据并保存成功回执、审计 |
| `role.manage_inheritance` | 修改普通 Role graph | 禁止 system Role、跨 workspace 和 cycle |

普通主体添加 Role 继承边时，还需满足原生 Role 转授前提：当前 Role 与用户的直接绑定含 WGO，且沿全部含 WGO 的有效继承路径到达待授予的 parent Role。移除边只要求 `role.manage_inheritance`，不额外要求 WGO。每个新请求由正式 Core 边界完成准入，然后按角色 ID 固定顺序锁定父子角色并校验当前 lifecycle。继承关系保存、GRANT/REVOKE、防环及并发一致性由 MatrixOne 负责；MOI 不执行全图 CAS、防环或深度、节点数、边数限制。

继承操作日志独立于执行锁和恢复机制：首次 `pending` 必须在 DCL 前持久化；明确成功写 `resolved`，明确拒绝写 `failed`，超时、断连或中断保留 `pending`。MO 已明确成功后日志收尾失败仍返回成功，并记录系统错误。同一工作区的相同请求编号只返回历史结果，输入改变则拒绝，不因当前关系变化重放旧 DCL。旧记录不阻塞新修改或角色删除；继承操作没有后台扫描、自动重试或重启恢复。其他 IAM 操作仍遵循各自恢复合同。

Frontend 将 Role 元数据、用户选择的初始 Application Policy 和 Data Privilege 一次提交给 `CreateRole`，保存阶段只有这一个写请求。Core 仅在全部权限落地且 `provisioning_state=ready` 时返回成功；创建未达到 `ready` 时返回失败并补偿半成品。Frontend 不追加权限写请求，也不轮询、展示或人工重试内部 provisioning 状态。

Role 编辑通过同一 `RoleWriteRequest` 和同一组 Saga phase 一次提交元数据、完整 Application Policy 与 Data Privilege，并同时校验 lifecycle、policy 和 data-privilege version。创建失败删除新 Role；编辑失败使用首个副作用前保存的 snapshot 恢复旧 Role、Policy 和 MatrixOne Data Privilege。Frontend 对响应丢失重用原 request ID，不串行调用独立 Policy/Data Privilege mutation，也不暴露部分保存状态。

Application Policy 与 Object Grant 的撤权遵循[新增授权与撤销授权](01-product-authorization-model.md#52-新增授权与撤销授权)：管理员可删除已不存在对象的历史授权，撤权不校验业务对象存在性；新增授权仍严格校验目标资源。角色编辑不能因移除历史授权而阻断同次提交中的其他有效变更。

历史 Application Policy 按当前 Registry 投影：未注册的 action，以及当前 action 已不支持的旧 scope，不参与点鉴权、集合过滤和角色权限视图，不阻断同一策略中的有效授权。忽略不产生任何 allow，也不把 exact 自动扩大为 all；Database、Volume、Table 仍支持的对象查看授权保留。读取不改写策略。角色成功保存时，以当前 Schema 校验后的完整配置替换旧 document 和 Grant Index；保存失败恢复原始快照，并发版本冲突仍拒绝覆盖。此兼容仅针对历史定义变化；新提交的未知 action、非法 scope、损坏的持久化结构、跨工作区/Role 的事实以及依赖故障仍拒绝，已明确登记的旧 action 改名继续保持原授权范围。

`superadmin` 只属于 workspace owner；`admin` 可分配给多个成员。只有它们是当前 Verified Effective Role 且 binding/lifecycle 校验有效时，Core 才对 Application IAM 全资源 allow；工作区初始化同时为对应 MatrixOne Role 物化完整的产品数据库/表权限，因此系统 Role 不需要逐对象读取 DCL 事实。普通 Role 仍必须满足 MatrixOne DCL。

## 4. 应用对象

本节所有 create action 均对 workspace 授权且可沿有效 Role graph 继承；业务对象按自身 lifecycle 成功提交后，幂等登记当前 Verified Effective Role 为 Direct Owner，登记成功后该 Role 获得对象的全部普通 Application IAM 能力。登记是新建对象成功的必要步骤；同库失败整体回滚，跨库失败保留原持久化操作且不能报告成功，详见[创建/删除一致性合同](04-storage-lifecycle-audit.md#33-ownership-登记与清理)。Ownership 只增加这项 allow，不定义业务对象存在性、readiness 或 lifecycle；不改变业务可见状态也不代表缺少其它 allow 的 Role 可以访问对象。普通应用对象的查看仅允许 `all`；使用、执行、修改、删除等其它 action 对可信 resolver 得到的具体对象授权，Policy scope 按该 action 的已登记范围选择 `all` 或 specific object。Catalog 数据树的查看及父 scope 创建例外见第 5 节。

canonical 应用对象的 target Ownership 缺失、non-active、畸形或字段不完整，不等同于资源不存在，也不是 deny 或依赖错误。显式 all/specific/parent/path grant 和当前已验证的 `admin`/`superadmin` 都不以 target Ownership 为访问条件；权限通过后必须执行 owner service 业务查询，由该查询按 workspace、稳定资源 ID、canonical 层级、逻辑删除和业务 lifecycle 决定 point 是否返回对象，并在 collection/list/tree/picker 的 count/pagination 前应用同一规则。picker 可以保留没有 Ownership 的对象，但不能伪造未知 Owner/version。

普通 Role 继续按自己的 Application Policy scope 裁决：显式 all/specific/parent/path grant 不要求 Ownership，restricted collection 在分页前下推对应 ID/parent/path；Owner 派生 ID 只在 exact-key、active 且完整的持久化 Ownership 匹配时增加 allow。缺失或异常 Ownership 不是独立拒绝条件；最终没有其它 allow 来源时按普通未授权处理。历史 exact-key 缺失记录的默认 Owner 是 workspace protected `superadmin`，由单次幂等补录物化；补录失败只写清晰日志，不改变功能或 readiness。只有直接操作或展示 canonical Owner/version 的接口校验相应 Ownership/CAS；Object Grant 的 `role.create` 或 `role.update` 路径不以目标 Ownership 为前置条件。本次实际采用的业务层级、workspace system Role、policy、storage 等必要事实不可用时仍 fail closed。完整合同见[存储、生命周期与审计](04-storage-lifecycle-audit.md#33-ownership-登记与清理)。

### 4.1 Connector

稳定 ID 为 Backend connector service 的 tenant-local `connector.id`。

对象存在性由业务行及其生命周期决定：产品读取、修改、探查和导入/导出依赖解析统一排除未完成创建或删除中的行；Ownership 不作为独立拒绝条件。新的删除请求只接受 active 行，并在状态写入时校验 active 条件及实际更新行数；pending 创建仍由原创建操作处理，deleting 行仍由原删除操作恢复。同库删除业务行、Ownership 与操作完成记录必须原子提交；历史跨库删除由原操作继续收敛必要收尾，失败不能写完成终态。

| Action | 授权层级 | 业务功能/API 分类 |
| --- | --- | --- |
| `connector.create` | workspace | `POST /newmoi/connectors`、`POST /newmoi/connectors/rest-api/probe`（未保存的 REST API 配置） |
| `connector.read` | object/collection | Connector list/get；list 在分页前过滤 |
| `connector.update` | object | Connector 配置、状态和元数据修改 |
| `connector.delete` | object | 业务删除与 Ownership 清理满足统一原子事务/持久恢复合同；不能把失败报告为成功 |
| `connector.use` | object/collection | files、Database/Schema/Table 探查、structured source 选择和运行期使用；`POST /newmoi/connectors/{id}/rest-api/probe` 和 `POST /newmoi/connectors/{id}/rest-api/preview`；REST 抽取在当前有效 extract assignment 下，仅对导入任务冻结的 Connector 执行 `connector.use` |

`POST /newmoi/connectors/validate` 是未保存临时配置 probe，只要求有效 membership，不读取已有 Connector。`/connectors/file/upload|download|stream|delete` 与 `conn_file_id` preview 分支属于临时候选文件 membership-only；一旦使用稳定 `connector_id`，产品 BFF 入口必须执行 `connector.use`。TraceSyncTask 是 Connector 的从属记录：列表可按过渡约定使用 `connector.read` 的 Core `ResourceAccessFilter`，且必须在分页前过滤；按 task ID 的读取、更新与删除由 BFF 完成对应 action 后，Catalog 非数据树接口信任可信 BFF 并执行业务处理。记忆执行方式也是 Connector 从属配置：读取 `builtin/workflow` 模式使用 `connector.read`，切换到 `builtin` 使用 `connector.update`；绑定自定义 Workflow 还必须由 BFF 对目标 Workflow 执行 `workflow.update`，仅持有 Connector 权限的投影不得返回 Workflow ID。当前不提供 Workspace 级默认记忆工作流。平台默认流程由平台 owner 发布为隐藏的 platform-managed Mowl Workflow，它不是用户可授权、编辑或枚举的 Workflow 对象；Catalog 不在每次 Session 执行前重复裁决 `connector.use`，后续实际进入 Database/Table 等数据边界时仍由对应 owner 独立鉴权。自定义记忆工作流只读验证入口要求 BFF 完成 `workflow.run` 与 `connector.use`；平台默认流程验证入口只接受 Connector 身份并要求 BFF 完成 `connector.use`，Workflow 身份必须从该 Connector 当前绑定的 platform-managed Version 解析，不能由请求提供。在读取 Session Case 和提交 Core/Mowl 执行前，不在 Catalog 重复执行产品 PDP；两种验证都使用可信 dry-run 写边界，不得落库。Connector allow 不授予目标 Database/Table 的 MatrixOne 权限。

### 4.2 Workflow

稳定 ID 为 workflow owner service 的 tenant workflow ID。execution、result、import context、node result、version 和 revision 是从属对象。

历史 execution 缺少创建时的主体或 Effective Role 时，升级将尚未结束的执行收敛为失败，保存 `execution_identity_unmigrated`；续跑和受控依赖访问必须拒绝。已经结束的执行及其原结果保持不变，不从当前 Default Role、角色名或异步上下文补写身份。身份来源不可用、身份不匹配、身份格式非法与未迁移分别记录稳定原因。

| Action            | 授权层级          | 业务功能/API 分类                                                              |
| ----------------- | ----------------- | ------------------------------------------------------------------------------ |
| `workflow.create` | workspace         | 创建、部署、clone/import 新 Workflow                                           |
| `workflow.read`   | object/collection | Workflow list/get、definition/version、execution/result/log                    |
| `workflow.update` | object            | 草稿、节点、变量、配置和内容版本修改                                           |
| `workflow.delete` | object            | 删除 Workflow，检查运行中 execution 与引用                                     |
| `workflow.run`    | object            | 启动、调试、retry/rerun/cancel execution；Lineage rerun 解析父 Workflow 后复用 |
| `workflow.manage` | object            | pause/resume、下线、显式版本切换等可运行状态管理                               |

批量运行的派发任务是Workflow的从属记录。`GET /newmoi/workflow/v2/workflow-apps/{workflow_id}/dispatch-jobs/{dispatch_job_id}`复用父对象的`workflow.read`，owner必须验证持久化任务的workspace及父Workflow与请求一致；不新增资源/action/Ownership。查询只返回派发状态和投递统计，不执行恢复、重试或取消，不返回运行身份、原始错误及源配置。派发完成与文件执行完成分别表达。运行收据的`dispatch_job_id`指明批量派发，实际执行由列表的`dispatch_job_id`关联；此时不得把历史`execution_id`提交标识用于执行控制。

会话 CLI 的草稿工程测试与提交复用既有候选 `test`、`submit` 产品 API；`project_files` 只承载工程内容。此模式必须绑定入口已验证的 live task proof，拒绝不匹配的 task/context/user/Role 与客户端测试状态；同步工程、编译、测试和提交仍逐次进入现有 Workflow 生成边界检查 `workflow.create`。实际结果由任务事件 owner 记录为不可见产品事件，原终态候选 owner 比对当前工程 digest 后消费，不新增资源、action 或客户端事件写入口。

已验证 live task 的公开工作流发布入口必须使用已测试并接受的候选，不能通过普通 `deploy` 的原始定义或 PATCH 的 DSL、表单定义、布局、设计图绕过工程测试与候选审阅；Workflow owner 在写入前返回 `WORKFLOW_CANDIDATE_REQUIRED` 和本地化的继续操作说明。候选解析和接受状态仍由既有 owner 验证，保持原 `workflow.create/update/manage` 边界，不从候选或 task proof 推导 allow。名称、触发配置和运行参数值可按上下文修改，已有工作流可独立运行、查询和核验；普通页面编辑与服务内部的托管工作流创建保留原合同。

测试临时资源的 ensure、observe、reset 入口同样绑定已验证的 live task：省略的身份字段从 proof 取得，显式提供但不匹配的 workspace/user/task/context/Role 必须拒绝，reset 只能清理当前任务。普通 Product 身份保留原显式 scope 合同；Catalog 选择仍是业务输入，实际建库、建卷和清理继续进入原资源生成边界，不从 task proof 推导数据权限。


`workflow.update` 与 `workflow.manage` 互不替代：PATCH 编辑内容只检查 `workflow.update`；显式启停与版本管理检查 `workflow.manage`。重新部署既有 Workflow 会同时替换内容并发布版本，因此在原有部署准入之外，必须同时检查该对象的 `workflow.update` 与 `workflow.manage`。

已接受的工作流候选若在接受时具有 owner 持久化的目标 Workflow 绑定，接受事实保存该目标，部署由同一 owner 解析为既有对象更新，并继续经过该对象的 `workflow.update` 与 `workflow.manage`；候选绑定只确定业务目标，不提供 allow。请求显式目标与该绑定不同时返回现有 proposal conflict，不创建或覆盖其它对象。没有目标绑定的新建候选保持原创建语义。

编写入口明确选择已保存 Workflow Version 或已有候选时，Workflow owner 将该基线的目标保存在既有 conversation authoring 记录中，新 proposal 在创建事务中继承目标；没有重新选择基线的继续编辑保留当前工程的选择。新建工程和明确选择无目标的新建候选不绑定既有 Workflow。MOMO 的记录只保存编辑目标，不重复保存 session authored files；源文件、模型说明或测试报告不能改写该目标。异步文件快照更新同一记录时保留目标，不得覆盖为旧内存值。上述记录只确定业务对象，实际读取和部署仍分别执行原生成边界的 read、update/manage。

候选发布查询同时识别不可变的创建候选，以及当前已发布版本中由 owner 写入的 `provenance.candidate_id`。手工定义携带的 provenance 不能建立候选关联。会话保存版本恢复优先使用该会话最新接受事实冻结的目标 Workflow，并返回该对象当前保存版本；另一会话发布新候选不改变原会话的编辑目标。目标不存在、处于非 active 生命周期或没有保存版本时不返回其它对象；存储读取失败继续返回错误。没有冻结目标的新建候选沿用创建会话及候选发布关联。保存目标不表示当前接受候选已发布，客户端确认修改候选已应用时仍核对当前版本的完整 task/artifact 引用。创建时的 `candidate_id/session_id` 不因修改版本而覆盖。上述关联只定位对象，列表仍在总数/分页前应用原 Core 过滤，定义/版本与执行读取仍走原 `workflow.read`，不得从候选关系推导 allow。

产品部署请求携带 `workflow_id` 时，该 ID 只用于部署已有对象；owner 查询不到对象即返回 HTTP 404 / `ErrWorkflowDeploymentTargetNotFound` 及本地化提示，不转入创建流程。发布事务持锁后仍须确认对象存在，防止查询后对象被删除。失败日志记录 workspace、workflow、actor、检查阶段以及 request/trace ID。未携带 ID 的首次部署与服务内部使用稳定 ID 的创建继续沿用原有创建流程，不拆分创建/发布事务，不查询删除回执。

自然语言编写入口加载已保存 Workflow 作为编辑基线时，在编写入口的 `workflow.create` 准入之外检查目标对象的 `workflow.read`。基线来自保存的 Workflow Version 和当前表单、布局，不依赖原创建者的私有会话、候选或 proposal；创建者字段不能追加拒绝。自然语言编写既可来自专用 Workflow 会话，也可来自 MOMO 等已接入创作能力的普通 chat；工作流基线准备、编译、测试与提交统一进入现有 Workflow generated Service boundary，不因 Agent 身份自动放行。MOMO 的创作文件位于其会话工作区，读写复用已准入任务的 Sandbox generated boundary；编译前的项目文件同步仍检查 `workflow.create`，不从工作区文件取得身份或权限事实。测试报告仍由原运行时 owner 绑定实际编译快照，工作区中可编辑的报告、客户端传入的“通过”或另一个项目的结果不能成为候选验收事实。编写历史按可信 workspace、会话实际绑定的 Agent、purpose 和 context 恢复，普通 chat 不改写或挂载为专用 Workflow session；入口权限通过后，历史、候选、源码及已应用记录不再按创建者追加拒绝。创建者和实际操作者用于审计；继续编辑使用当前请求已验证的身份，既有任务的运行身份保持冻结，实际应用修改继续执行既有部署权限。

会话工作目录是任务私有运行数据，不是独立授权的应用对象。执行入口从已冻结的任务解析 workspace、actor、context，并在准备工作目录之前及执行命令之前重新进入 `agent.use`。Sandbox owner 只接受该可信作用域，按会话校验目录归属；Bash 与通用 `apply_patch` 使用同一目录和相同的任务准入，补丁不经过 Workflow 业务服务、不签发额外凭据，且不能通过路径或符号链接越过目录；目录根、对象存储 key 和恢复版本不能来自模型参数。文件与清单通过平台 FileService 写入私有 S3，Sandbox 的系统库表只保存恢复索引、版本和后台保存状态。每轮用户任务结束后最多请求一次异步快照；单次命令、文件读写和定时器不触发快照。后台任务仅携带 workspace/context/task 引用，由 Sandbox owner 恢复私有目录事实，不能携带凭据或旧授权结果；快照未成功时不得回收对应 OpenShell。会话读取、消息历史和任务状态查询均不准备目录、不创建执行环境。实际命令或补丁执行才使用明确配置的本地执行环境或 OpenShell；本地执行仅在部署配置为 local 且未启用 OpenShell 时选用，不因远端错误自动切换。恢复不延续旧凭据或旧 allow 结果，数据操作仍通过当前任务身份进入正式业务 Service。

用户/BFF 发起业务 Task 时，入口按可信 Workflow 对象执行 `workflow.run`（或其明确的入口业务 action）PDP。唯一已登记的 `moi:workflow.trigger -> Catalog POST /api/v1/workspaces/:id/tasks` 是该已准入 Task 上下文的 child-Task sender：专用 `GetForTaskContinuation` 只在可信 system transport 下发送冻结 actor/workspace/Verified Effective Role 和 admission 元数据，Catalog 非数据树 Task receiver 信任该可信调用，不校验 continuation 或再次调用 Core `workflow.run`，只处理 `workflow_version_id` 等业务输入和事务完整性。它不新增 `workflow` action、Registry 条目、签名 grant 或 `task_id`/`case_id` capability；child Task 后续访问 Connector、Volume、Table、Database、MatrixOne 等依赖时仍按各自资源合同重新鉴权。

Workflow create Saga 在 System DB 以业务 `pending`/等价状态持久化 `workflow_app`，完成定义、版本和必须的运行期准备后用版本 fence 切换为 `active`；该 business lifecycle 不得命名或解释为 `pending_owner`。业务激活前以持久化的 Verified Effective Role 幂等登记 Ownership；跨 System/Tenant 写入复用同一个原业务 intent，登记失败不能激活或完成该 intent。runtime post-commit action 仍按业务合同向前恢复，已持久化的 cron task 按同一 task/spec 幂等恢复。尚未发布 version 的 disabled Workflow 使用 operation 派生的内部业务 fence，不能暴露成有效 version。Workflow point read、collection、execution list、file execution 投影和内部运行入口只读取业务 lifecycle；Ownership 缺失时 Owner 来源不命中，其它来源照常裁决。补偿只能依据业务 operation fence 删除本 Saga 新建且尚未激活的行，不能依据 Ownership 状态删除既有或已激活 Workflow。

候选部署在任何创建副作用前检查必填运行参数，拒绝时返回稳定错误及缺失字段；无自定义算子的创建同样先持久化原业务 intent。业务重试和恢复使用其中冻结的 request/trace/Effective Role，不把新的 HTTP trace 当作原操作身份。历史缺陷留下「业务对象及创建 intent 均不存在、但同一候选派生 request ID 的 Ownership 已成功」时，Workflow owner 只可在当前创建准入通过后，通过 IAM owner 读取并冻结原创建回执；IAM 必须核对 workspace、资源、创建主体、Effective Role、归属、成功 operation 与审计的一致性。激活前再次核验同一回执，保留原归属和审计，不覆盖旧 payload/trace、不放宽普通注册的幂等校验，也不处理其他主体或 Role 的残留。新的部署输入由本次业务 intent 单独记录。

Workflow 删除使用 durable forward-recovery Saga：

1. Core 按 `workflow.delete` 校验，并用与实际删除相同的 System DB 规则预检运行中 execution、open volume delivery 和 open volume dispatch job；同时冻结 case state（包含其持久化 manifest 中的精确 file ID）、cron task 和 dynamic-service version 的 cleanup receipt，先写入 durable Saga context。终止性业务冲突必须在 business lifecycle 变化前返回。文件清理只能依据 manifest file ID、持久化的 `source + source_session_id` owner 或 case-scoped state path，不得根据文件名推断归属。
2. 预检通过后，在 System DB 将 Workflow 的业务 lifecycle 标记为 `deleting`，由 Workflow owner query 立即阻止新的普通访问和执行。Ownership 清理属于原删除操作的必需收尾；确认缺失可幂等继续，存储或 CAS 失败必须保留错误与恢复状态。
3. System DB 删除 Workflow 及其按删除规则允许清理的关联业务数据；删除事务必须重新计算 cleanup receipt 并与 durable receipt 精确匹配，发生漂移时回滚。若预检后出现新的终止性业务冲突，只补偿 Workflow 自身的 business lifecycle，并记录可重放终态，不依赖 Ownership version。
4. 业务数据删除成功后，Saga 按 durable receipt 幂等清理 case state、cron 调度和 dynamic-service worker；任何业务清理失败都保持可恢复状态。specific grant 与 Ownership 清理同样必须完成后才写原操作的成功终态；失败保留原 intent 向前恢复，也不得重新暴露已删除对象。
5. 瞬时业务失败保留可判定的 Saga 状态；Catalog 启动时及后台周期扫描按原 request ID 继续未完成的业务删除。Ownership 收尾失败与其它未完成步骤一样由原操作恢复，不能用日志替代完成。终止性业务冲突完成 lifecycle 补偿后，新的 request ID 可以在阻塞条件消失后重新发起删除。

Saga 的 durable context 至少记录 resource type/ID、workspace ID、operation type/ID、当前步骤、actor principal、Verified Effective Role、request ID、trace ID、重试次数和最后一次安全错误。后台重试只能调用 Core 受信任 lifecycle mutation boundary，不得用 system credential 伪造用户 principal，也不得自行选择 Role。

Workflow action 不覆盖 Volume、Table 或 MatrixOne 数据依赖。BFF 在提交入口完成 Connector、Model Backend、Agent、Compute Resource 等产品业务 action；内部执行不重复这些业务 PDP。提交时记录 canonical dependency 与 Effective Role；Mowl 内部延续只在进入 Catalog 数据树或 MatrixOne 时，以随调用传递的冻结 Effective Role 作为唯一 Role 输入，再按数据 owner 的 canonical resource/action 裁决，见[请求级授权裁决复用](11-request-authorization-decision-reuse.md)。

revision rerun 必须带可解析的 target output emission，并由 owner service 将 emission 解析到父 Workflow 后执行 `workflow.run`。无 target 的入口没有唯一授权资源，不能作为公开 Backend/Product SDK 能力保留，也不能在 handler 中隐式选择第一个 emission。

Workflow Template 当前不注册 `workflow_template.*`，也不登记 Ownership。`/newmoi/workflow-templates*` 只要求可信 workspace 的有效 membership：内置模板对成员只读，自定义模板按 Backend 记录的 `workspace_id` 隔离，写操作继续受 reserved admin/owner 规则约束。模板可见不产生 `workflow.create/run` 或模板引用资源的 allow。

### 4.3 Custom Operator

稳定 ID 为 Core `custom_operator.id`。API Service 是独立产品资源；Custom Operator 可以作为 API Service source 或版本固定的 Workflow 依赖。准备已保存 Workflow 的编辑工作区时，复制其精确引用的可编辑公共算子源码必须校验对应 `custom_operator.read`；历史候选使用候选自身冻结的源码快照，不能从当前公共库替换历史源码。

| Action                   | 授权层级          | 业务功能/API 分类                                                                                                   |
| ------------------------ | ----------------- | ------------------------------------------------------------------------------------------------------------------- |
| `custom_operator.create` | workspace         | 创建 Custom Operator                                                                                                |
| `custom_operator.read`   | object/collection | list/detail/source view                                                                                             |
| `custom_operator.update` | object            | 元数据、源码、enable/disable                                                                                          |
| `custom_operator.delete` | object            | 删除指定 Operator/version                                                                                           |
| `custom_operator.run`    | object            | test-run                                                                                                            |
| `custom_operator.use`    | object            | 作为 API Service source 或 Workflow 依赖；发布期校验并冻结 canonical dependency，运行、恢复、重试和破坏性提交前重验 |

活动 Agent 任务的 `moi-cli` 可以通过普通 Custom Operator 产品入口发现、创建、读取源码、修改和测试正式算子。入口恢复冻结的唯一 Role 后，仍由生成代理执行上述 action、Ownership 与依赖授权；任务签名不是算子创建或运行权限。源码文件留在会话工作区，CLI 只把所选源码作为现有请求内容提交，不采用镜像内的旧版 CLI 或服务凭据。

Workflow Agent 创建阶段的临时算子不是 canonical `custom_operator` 产品对象。Agent create 必须在当前请求以冻结的 Verified Effective Role 对 workspace 父级重新执行 `custom_operator.create`，但成功后只写 `(workspace_id, authoring_task_id, user_id)` 精确约束的 task-private `workflow_operator_draft`，不登记 Custom Operator Ownership，也不进入普通 Catalog/Search、WorkItem Catalog、API Service source 或无 authoring context 的 resolver。Candidate 只冻结实际引用 draft 的 server-owned immutable source/schema/handler/digest snapshot；Accept 只记录 candidate acceptance，本身不创建正式算子。

保存或发布 `workflow_app` 时，owner 解析并验证 accepted candidate bundle；只有 bundle 含实际引用的 custom operator snapshot 时，才发布到现有 canonical `custom_operator`。生成和修改始终使用 task-private `draft`；发布将该 snapshot 投影到正式 `v1`，并同步保存的 Workflow 节点引用，不能把 `draft` 原样写入公共库。首次发布执行 `custom_operator.create`，算子与同一 Verified Effective Role 的标准 Ownership 在 tenant 同库原子创建。再次发布执行现有对象的 `custom_operator.update`，替换源码、schema 和元数据，保持原 ID、创建信息及 Ownership；相同内容可幂等复用，不因为内容修改而拒绝发布。非 draft 的已固定版本 snapshot 仍只允许相同内容复用。跨库或对象存储副作用复用原持久化操作；发布失败必须返回错误。该 operator 是现有运行路径下的正式资源，不是第二套 runtime identity。

`workspace_visible=false` 只控制 discovery：普通 Custom Operator list/search 和 WorkItem Catalog 必须在 count、pagination 和 merge 前过滤 hidden row；它不改变 operator identity、Ownership、`custom_operator.use` 或运行期依赖授权。现有 exact `node_id + version` lookup 继续解析 hidden row，并继续受对应 IAM collection/runtime dependency 合同约束。本生命周期不新增公开 visibility mutation 或 workspace share 接口。记忆治理 Workflow 只接纳实现 `Memory Custom v2` 固定安全契约的 Custom Operator：运行时只投影允许的 Session Trace 数据和直接上游 `dict`，节点配置通过独立的 `config` 参数传入，并仅合并到该节点的隔离输出；Workspace、Consumer/subject、Connector、可信 Run 绑定、授权声明与凭证不得暴露或覆盖。Builtin WorkItem Catalog 不属于本资源，也不要求任何 `custom_operator.*` action。

### 4.4 API Service

API Service 的稳定 ID 是 `sha256(workspace_id + "\\0" + node_id + "\\0" + version)` 的 `api_` 前缀截断摘要。该 ID 同时是内部 WorkflowApp 的权威映射；重发布更新同一个 WorkflowApp 的版本，不能因 request ID 创建同名的第二个 dynamic-service workflow。业务记录、状态/版本、WorkflowApp 映射与 Ownership 按统一创建一致性合同共同完成；任一步失败不能返回成功，也不能由 Backend 的通用 `BusinessActionAuthorized` 标记推导授权或完成状态。

| Action | 授权层级 | 业务功能/API 分类 |
| --- | --- | --- |
| `api_service.publish` | workspace | 按 trusted `node_id + version` 发布或重发布 API Service；可沿有效 Role graph 继承 |
| `api_service.read` | object | 查询已发布 API Service |
| `api_service.manage` | object | 启用或停用已发布 API Service |
| `api_service.run` | object | 调用已发布 API Service |

发布时 BFF 完成 `api_service.publish` 及其必要依赖的产品 allow/deny；Catalog 非数据树接口只解析可信 WorkItem identity、重算 API Service ID 并执行生命周期/业务写入，不重复调用这些 Core PDP。空 `compute_resource_id` 表示未绑定具体 Compute Resource，使用平台默认执行行为；它不是可枚举资源，不产生 `compute_resource.use` dependency。实际进入 Compute、Catalog 数据树或 MatrixOne 数据面时，才由对应 owner 独立鉴权；Catalog 仍必须校验 request/config 中的 compute resource 与 source 的业务一致性。

调用时 BFF 完成 `api_service.run`；Catalog 非数据树接口不重复裁决该 action。显式绑定的 Compute Resource 在实际进入其受保护 owner 时独立鉴权；未绑定服务不产生 Compute Resource runtime fact。该 path 不接受调用方伪造的 Workflow owner metadata，并保持 worker-backed service 的 readiness gate。

工作区平台 MCP 发现、导入与按服务名调用同时支持算子 API 和普通 Workflow 动态服务。
共同调用入口由 owner 从当前发布记录解析来源：算子 API 使用其 canonical API Service ID
执行 `api_service.run`；普通 Workflow 服务使用真实 Workflow ID 执行 `workflow.run`。
两类来源互斥，不能把缺失 canonical ID 的损坏算子 API 降级为 Workflow 服务放行。
服务描述只用于展示，缺失描述不改变来源、授权事实或可调用性。

### 4.5 Compute Resource

稳定 ID 为 Core tenant compute resource ID。平台 spec 管理不属于本资源。

会话 CLI 的 workspace 实例 create/list/get/update/delete、worker images、delete preflight、runtime 与 suspend/resume/retry 复用 live-task 身份入口；enabled spec list 同样按当前任务 workspace 的有效 membership 读取。任务 proof 只恢复冻结的 Role 候选并重验 active task 与 `agent.use`，实际实例操作、集合过滤、Ownership 和 lifecycle 仍由原生成边界裁决，不授予隐式 `compute_resource.use`。平台规格管理、`/admin/compute-resources` 和历史 Ownership adoption 继续使用原普通产品身份入口，不从会话任务推导平台管理员身份。

| Action                     | 授权层级          | 业务功能/API 分类                                     |
| -------------------------- | ----------------- | ----------------------------------------------------- |
| `compute_resource.create`  | workspace         | 创建 Compute Resource、读取创建表单所需 worker images |
| `compute_resource.read`    | object/collection | list/get、metrics、delete preflight                   |
| `compute_resource.update`  | object            | 修改实例配置                                          |
| `compute_resource.delete`  | object            | 删除实例与 lifecycle cleanup                          |
| `compute_resource.use`     | object            | Workflow/Agent/任务选择和调度使用                     |
| `compute_resource.operate` | object            | suspend/resume/retry 等运行状态操作                   |

Compute Resource List/Get 必须先以 `compute_resource.read` 调用 Core 生成 owner access plan，再执行业务查询。Core 复用同一 `ResourceAccessFilter` 计算 canonical read scope：canonical `compute_resource.read.all` 与已验证 system all-access 物化为 `all`；Owner 派生 scope 从 active Ownership inventory 得到受限 ID，不再接受显式 exact read grant。受限 ID 下推 storage，`empty` 不访问 storage，`all` 执行普通 owner SQL；当前 Compute bounded plan 不登记 parent/path query shape。三种 shape 都必须在 count 和 pagination 前应用，不能由 handler 本地补做授权过滤。

List/Get 响应中的 `allowed_actions` 候选集合固定为排序后的 `compute_resource.update`、`compute_resource.delete`、`compute_resource.operate`，合法 deny 返回 `[]`。每个 action 的 canonical all scope 可以使用 `uniform_allow`；其余 action 只对 SQL 实际返回的资源做 candidate 投影。Owner 派生 read plan 保存 active Ownership snapshot，并用最多 100 ID 的 strict exact-ID batch 生成 opaque proof；显式 `read.all` 不保存该 snapshot。

canonical `read.all` 结果的 candidate action 只匹配 canonical all、显式 exact specific 或 Owner 派生来源：Ownership 缺失或 non-active 的行仍可获得匹配的显式 exact update/delete/operate，只是不增加 Owner 派生 action；某一 action 自身具有 canonical `all` 时仍独立 `uniform_allow`。当前 owner query 未返回 parent/path，因此 bounded projection 不宣称支持这两种 candidate scope。Core 只对已经采用的 Owner 派生子集重读并比较 Owner、status、version 等完整事实；该子集的读取故障、非法响应或并发漂移不得产生相关 allow，按[失败语义](01-product-authorization-model.md#9-失败语义)分类，普通对象没有 Ownership 不属于依赖故障。read 和共同事实仍有效时，局部可控的 candidate 异常只取消对应动作，不能使整个业务读取失败。

响应前必须对完整结果集重验 policy、Role Graph、binding 与 lifecycle；零行和 detail not found 也不能跳过 final fence。List/Get 不执行历史 Ownership lazy repair；没有 active Ownership 的对象不进入 Owner 派生子集，也不会使计划失败。对已经采用的 Owner 记录，strict reader 缺失、集合不完整/额外/重复/错键、坏版本、repair state 或授权事实漂移时才 fail closed，不能退回 point read。显式 exact specific scope 不进入 Ownership proof。`allowed_actions` 只用于展示，不授予 `compute_resource.use`，也不能替代 mutation 的实时 point Authorize。

Compute Resource Spec 是平台 catalog capability，不注册 `compute_resource_spec.*`。enabled spec list 只要求当前 workspace 有效 membership；management-permission、create/update/enable/disable 只由 Core `spec_admin.accounts` 控制。`compute_resource.create` 不能授予规格管理权限。

历史 Compute Resource 的 point authorize 对显式 all/specific/parent/path grant 或当前已验证 `admin`/`superadmin` 都不以 target Ownership 为条件；随后执行的 owner 查询必须精确匹配 workspace/ID 并应用 lifecycle 条件，collection 在分页前应用同一 canonical lifecycle 白名单。Owner 派生 scope 在缺失、non-active 或畸形 Ownership 时只是不命中 allow，不产生额外错误。`terminating`、`deleted`、未知 lifecycle 或业务 storage 读取失败仍由 owner 查询拒绝/报错。SuperAdmin adoption 和删除 lifecycle 是独立的 Ownership mutation，仍要求受保护 helper、CAS 与审计，不接受调用方指定 owner，也不由普通 read/list/runtime 自动执行。

## 5. Catalog、Database、Volume 与 Table

可信层级为 `workspace -> catalog -> database -> volume/table`。名称和路径不是 IAM identity；Catalog owner service 必须解析稳定 ID、workspace、parent 和 lifecycle。Database 下的 Table/Root Volume 导航分别使用 `database.show_tables` / `database.show_volumes`，具体 Table 数据与元数据访问仍使用 `table.query`，具体 Volume/文件访问仍使用 `volume.read`。

Catalog、Database、Table 的集合接口和单对象点查遵循不同返回语义。集合请求结构合法且可信父资源存在时，
Core 先用同一 `ResourceAccessFilter` 在 count/pagination 前过滤；没有可见资源时返回 `200` 空集合，不能因
无权项被过滤而返回 `403` 或 `404`。`/catalog/database/table-leaves` 使用 `table.query`，
`/catalog/database/children` 使用 `database.show_tables` / `database.show_volumes`，两者没有可见子项时都返回
`200` 空列表，不额外附加 `catalog.show_databases`。可信父 Catalog/Database 不存在、已删除或无法解析时仍返回
`404 ErrObjectNotFound`。`catalog.info`、`database.info`、`table.info` 等点查对无权对象继续用
`404 ErrIAMResourceNotFound` 隐藏存在性；依赖故障按 `5xx/503` 返回。

### 5.0 已保存 action 的兼容

Application Policy 中的 action ID 和 resource type 是持久化合同。Native Catalog 的
`catalog.create/read/update/delete`、`database.create/read/update/delete`、`volume.create`
必须同时识别下文对应的历史 action。对应关系由业务 Service 的 action 注解声明，生成的同一
Core Registry 校验历史 grant 并为 point Authorize、ResourceAccessFilter 提供等价事实；
不改写策略文档、Grant Index、版本或审计身份。

`workspace.show_catalogs` 到 `catalog.read`、`catalog.show_databases` 到 `database.read`
仅在历史 `all` scope 下等价；不得将 exact、parent 或 path scope 跨资源类型转换。
其余改名保持原 resource type 与 scope。新名称保存的策略继续有效，新输入的未知 action 或非法
scope 仍失败关闭。历史 `workflow.update` 保持独立编辑权限，不转换为 `workflow.manage`。

### 5.1 Catalog（Directory）

| Action | 授权层级 | 业务功能/API 分类 |
| --- | --- | --- |
| `workspace.create_catalog` | Workspace，`all` only | 创建 Catalog，可沿有效 Role graph 继承 |
| `workspace.show_catalogs` | Workspace，`all` only | Catalog list/info/ref-list 与目录元数据展示 |
| `catalog.update_catalog` | Catalog，`all` 或 specific resources | 修改 Catalog |
| `catalog.delete_catalog` | Catalog，`all` 或 specific resources | 删除 Catalog，先检查 active child 和仍有效的业务约束；Ownership 缺失不阻断删除 |

历史 active Catalog 的补录只查询 exact-key Ownership 完全不存在的对象，并登记默认 `superadmin` Owner；已有任何 exact-key Ownership 都保持原样。补录只是元数据补全，不参与任何功能、授权 gate 或 Catalog readiness：缺失时 Owner 来源不命中，其它授权来源照常裁决。每个 workspace 每次启动只执行一轮；candidate inventory、workspace system Role facts、tenant transaction、writer/readback、rollback、workspace 枚举或上下文失败都记录结构化失败类型、处理进度和原始错误并继续启动，本进程不重试，下一次启动再幂等查询。正常 Catalog 创建必须连同实际创建 Role 的 Ownership 完整完成，遵循统一创建一致性合同；不能先提交业务再忽略登记失败。历史路径不读取 `created_by`，也不修改 Data Share migration/offset。

### 5.2 Database

| Action | 授权层级 | 业务功能/API 分类 |
| --- | --- | --- |
| `catalog.create_database` / `database.create` | parent Catalog | MOI 入口只允许在获准的 Catalog 内创建 Database；指定 Catalog 和 `all` 均向该 MO Role 物化账号级建库权限，SQL 入口不受 Catalog 范围限制（见 §5.5） |
| `database.read` | Database，`all` 或 specific resources | list/info/ref-list 与 Database 元数据展示；列表先按获准 Database 过滤，详情必须校验目标 Database，不能仅检查父 Catalog 的查看权限 |
| `catalog.show_databases` | 历史全局授权 | 保留已保存的全量 Database 查看语义；新的指定对象授权使用 `database.read` |
| `database.show_tables` | parent Database，`all` 或 specific resources | 按 Database 授予直接 Table 子项导航能力；具体 Table 查看、查询仍受对应对象权限控制，不替代 `table.query` |
| `database.show_volumes` | parent Database，`all` 或 specific resources | 按 Database 授予直接 Root Volume 子项导航能力；具体 Volume 查看仍受 `volume.read` 对象权限控制 |
| `database.update_database` | Database，`all` 或 specific resources | 修改 Database 元数据 |
| `database.delete_database` | Database，`all` 或 specific resources | 删除 Database；Core 先以当前 Verified Effective Role 完成 exact 授权和审计，再由受控 system connection 执行 MatrixOne `DROP DATABASE`；若 MO 仍存在该 Database 的 Data Share publication，则 preflight 拒绝删除。Database 业务 lifecycle 独立推进，Ownership 缺失或异常均不阻断删除 |
| `database.create_table` | parent Database | MatrixOne Table create 的数据面能力 |
| `database.grant.create_table` | parent Database exact | 向目标 Role 转授 create-table 能力，使用 exact grant scope |
| `database.query` | Database exact | 整库读取；Data Privilege 显式授予或撤销同库 `SELECT ON TABLE <db>.*` 与 `SHOW TABLES ON DATABASE <db>`，适用于普通库和订阅库，不接受行列规则 |
| `database.grant.query` | Database exact | 整库 SELECT 的委派管理 action；使用现有数据委派准入，不作为数据读取授权 |

Database 删除的单次用户请求不在后台重放：每个业务 Saga step 只执行一次，Core durable delete intent 尚未确认时失败即终止，用户使用新的 request ID 再次发起。删除 intent 只持久化 Database 自身的业务 lifecycle、稳定资源身份、operation 和外部 DDL 恢复上下文，不读取、锁定或推进 Ownership 状态；exact-key Ownership 缺失、non-active、畸形或冲突都不影响 intent 和 `DROP DATABASE`。只有业务 intent 已明确提交后，Backend 才在进程启动时对未完成业务状态执行一次前向一致性修复；该修复不重新授权或重新创建用户操作，也不进入周期轮询。错误契约必须区分删除未开始、intent 已提交、`DROP DATABASE` 结果不确定、物理库已不存在但 finalization 未完成和 durable state 损坏；Core 使用稳定 `moi-core.catalog.database_delete` domain、reason 与 phase metadata，Backend 转换为稳定公开错误码，禁止用统一 503 或错误文本推断是否重试。终态日志必须携带 phase/outcome、workspace/catalog/database/Saga/operation/correlation 标识并明确记录未安排自动重试。Database 删除确认 MatrixOne 对象已不存在后，Catalog owner service 在删除 Database 元数据的同一 tenant transaction 内，集合清理该 Database 和全部子 Table 的 Data Privilege 状态，并对每个受影响 Role 推进一次 CAS 版本；specific grant 始终清理，Database/Table Ownership 必须按原删除操作完成清理；确认缺失是幂等结果，清理失败保留原操作并返回错误。MatrixOne 权限目录中指向已删除对象 ID 的残留行不构成当前授权，读取权限视图时必须按当前 Database/Table 对象事实过滤；同名重建对象不会继承旧对象权限。当前实现仍维护 `ownership_state=deleting/absent` 并让部分异常状态阻断删除，属于 implementation contract gap，不是目标合同。

### 5.3 Volume 与文件

Root Volume 稳定 ID 来自 Catalog Volume；Folder/File/File Artifact 通常继承 canonical root Volume。Data Asset 的内部 manifest、derivation、解析结果和 lineage 是 Catalog 服务实现状态，不是 root Volume 的从属 IAM 资源，也不注册 `data_asset.*` action。

文件真实存在、属于当前 workspace，且 Core 确认未挂载任何 Volume 时，当前 workspace 的有效成员即可访问，不要求 `volume.read` / `volume.write`，也不要求调用者是上传者、Owner 或 Admin/SuperAdmin。该规则适用于所有未挂载文件，不限于某个临时上传入口；缺少 Volume 挂载本身不能被解释为文件不存在或无权访问。文件不存在、属于其它 workspace、成员身份无效或无法可靠确认挂载状态时仍拒绝访问；元数据查询失败和挂载关系异常不能当作“未挂载”。

工作区文件 `model-url` 签发入口同样支持已认证的任务子进程：先验证活动任务及 grant，恢复冻结的 Effective Role，再按上述文件归属和挂载事实授权。签发后的 `catalog-files/{file_id}/content` 是外部模型使用的短期签名数据面，只验证单文件 capability，不要求 Product 登录，也不把 runtime 身份头作为该 capability 的替代。完整边界见[请求与运行期合同](03-request-runtime-contracts.md)。

文件产物单查与批量解析也遵循此分类：Core `catalog-files/:file_id/asset`、`catalog-files:batchResolve` 在业务读取前复用同一文件存在性及挂载解析器。混合批次中的未挂载文件消费请求计划的 Verified Effective Role，已挂载文件按去重后的 Root 执行精确 `volume.read` 门禁；任一文件不存在、归属无法确认或 Root 被拒绝时，整批不执行产物读取。

已挂载文件的产品入口通过 Core Volume owner 的请求级批量准备接口完成 `volume.read` / `volume.write` PEP。BFF 传递源标识与服务端选择的 action；Core 解析 canonical Root、去重并补充数据树计划。该接口不增加资源或 action，不把普通业务准入转换为数据 allow，也不要求 BFF 先逐 Root 调用普通 `Authorize`。文件挂载到 Volume 后切换为目标 Root Volume 权限，原有成员准入不能继续作为该文件的 `volume.*` allow，也不能授权挂载操作本身。

同一顶层 BFF 请求中的文件访问按 canonical Root Volume 与 action 去重。Core 批量生成未覆盖 Root 的精确计划；后续文件接口只匹配计划，不按文件重复验证 Role 或执行完整 PDP。`volume.read` 与 `volume.write` 分别覆盖，同 Root 不等于跨 action allow；新 Root 必须补充。计划可以跨该请求的 Catalog 子接口复用，请求结束即失效。Admin/SuperAdmin 携带可信 Verified Effective Role 时在权限准备和目标元数据解析之前直接取得全量范围，实际业务读写仍校验对象事实。闭合传输与集合/点查隔离见[请求级授权裁决复用](11-request-authorization-decision-reuse.md#顶层-bff-请求的数据树计划)。

历史 active Root Volume 的补录只查询 exact-key Ownership 完全不存在的对象，并登记默认 `superadmin` Owner；已有任何 exact-key Ownership 都保持原样。补录只是元数据补全，不参与任何功能、授权 gate 或 Catalog readiness：缺失时 Owner 来源不命中，其它授权来源照常裁决。每个 workspace 每次启动只执行一轮；candidate inventory、workspace system Role facts、tenant transaction、writer/readback、rollback、workspace 枚举或上下文失败都记录结构化失败类型、处理进度和原始错误并继续启动，本进程不重试，下一次启动再幂等查询。正常 Root Volume 创建必须连同实际创建 Role 的 Ownership 完整完成，遵循统一创建一致性合同；不能先提交业务再忽略登记失败。历史补录不读取 `created_by`。

| Action | 授权层级 | 业务功能/API 分类 |
| --- | --- | --- |
| `database.create_volume` / `volume.create` | 当前入口的 parent Database | 创建 Root Volume；指定父容器的创建授权只覆盖该父 scope，不扩大为 workspace 全局能力 |
| `volume.read` | object/collection，`all` 或 specific resources | 按指定 Root Volume 控制 Volume/Folder/File list、info、download、stream、preview、artifact resolve/backfill |
| `volume.update` | object | 修改 Root Volume 元数据 |
| `volume.delete` | object | 按统一删除一致性合同完成业务删除与 Ownership 清理；失败保留原操作且不能报告成功 |
| `volume.write` | object | Folder/File create/update/delete、upload、attachment mutation、agent artifact batch-delete（标记成果已删除并解除当前 Catalog placement） |

普通 Role 访问已挂载文件时，route 必须先通过 containment resolver 归一到 canonical root；未挂载文件按上述 workspace 成员规则准入。面向 MOI actor 的 download、stream、preview、runtime-files 和用户 temporary URL 不是永久 capability；这些路径的实际读取遵循相同的挂载分类，已挂载文件仍需当前 actor/Effective Role 的 `volume.read`。给外部模型拉取的 Catalog 文件 HTTPS capability URL 沿用单独登记的合同：签发入口要求 Verified Effective Role，并对系统私有 Catalog hierarchy 中的文件执行 `volume.read`；普通 Volume 文件不走该私有检查。拉取时只验签名和 TTL，见[请求与运行期合同](03-request-runtime-contracts.md#5-durable-execution-context)。

Workspace 级文件列表是 Volume 容器关系的 collection projection，不是脱离 Volume 的第二套 File 权限模型。Core 必须先用当前 actor 和已验证 Effective Role 调用 `ResourceAccessFilter(volume.read)`，再把获准的 canonical root Volume ID 及其未删除子 Volume 作为数据库查询范围；该范围必须在 `COUNT` 和分页之前生效，空范围直接返回空结果。列表的稳定行语义是 File 在 Volume 中的一条 placement；同一 File 同时关联多个获准 Volume 时可出现多行，每行必须返回对应 `volume_id`。未关联到获准 Volume 的孤立 File 不可通过该列表暴露。Agent 成果中心是独立持久化的 runtime Artifact 索引：列表和详情在 `COUNT`/分页前用 `volume.read` scope 过滤成果记录保存的原 `volume_id`，并从成果记录读取文件名、路径和版本。Catalog placement 被删除或移动不会删除成果记录，也不能改选同一 File 的其它 placement。预览和下载文件内容时仍由 Catalog 按当前 actor 和 Effective Role 重新授权；添加到知识库时还必须校验当前精确 placement。原 Volume 已删除或不再可读时，成果元数据不向该 Role 展示。

Data Asset 内部 manifest、derivation、parsed manifest、resolve 和 lineage 路由只消费可信 transport，并在打开存储前校验 workspace tenant；它们不要求 execution contract，也不以关联 Volume、File 或 Semantic Model 派生 `volume.*`、`semantic_model.update` 或其它 Data Asset action。此例外不改变实际数据资源门禁：任何返回、解析或批量解析已挂载 canonical File/Volume 的 Data Asset alias，仍须先解析 canonical root Volume 并执行 `volume.read`；system-only containment resolver 只返回 root identity，不形成 allow。

### 5.4 Table 与 MatrixOne

Catalog 读取表详情或预览时，若读取失败且以工作区管理连接确认普通物理表已不存在，Catalog 同步删除该稳定 Table ID 的元数据，并由 IAM 在同一租户事务清理 Ownership 和写入审计，提交后返回 `ErrNotFound` / 404，中文提示“表不存在”。清理失败返回系统错误并回滚元数据删除。权限拒绝、连接故障及订阅关系不可读不能作为物理表不存在的证据；不触发该清理。

| Action | 授权层级 | 业务功能/API 分类 | 最终执行边界 |
| --- | --- | --- | --- |
| `table.query` | object/collection | Table 元数据和 SELECT/查询数据 | MatrixOne DCL/row-column rule；Core 将精确表 SELECT 或所属 Database 的真实整库 SELECT 事实投影为 Catalog stable Table ID。它负责具体 Table 的元数据和 SELECT，不负责 Database 子项导航 |
| `table.insert` | object | INSERT | MatrixOne DCL/row-column rule |
| `table.update` | object | UPDATE | MatrixOne DCL/row-column rule |
| `table.delete` | object | DELETE | MatrixOne DCL/row-column rule |
| `table.grant.query` | object exact | 转授 query | Core PAP + MatrixOne DCL projection/readback |
| `table.grant.insert` | object exact | 转授 insert | Core PAP + MatrixOne DCL projection/readback |
| `table.grant.update` | object exact | 转授 update | Core PAP + MatrixOne DCL projection/readback |
| `table.grant.delete` | object exact | 转授 delete | Core PAP + MatrixOne DCL projection/readback |

`/roles/{role_id}/data-privileges` 对目标普通 Role 授予或撤销 MatrixOne 数据权限。Core 使用与对象授权相同的五种独立来源：当前已验证的 `superadmin`、`admin`、workspace `role.create`、workspace `role.update`，或每个目标对象的 canonical active Ownership。普通角色沿 active Role graph 继承到的 Owner 仍只覆盖同一 exact 对象。整批变更必须全部通过；任一对象未授权时拒绝整批写入。

`table.grant.*`、`database.grant.query` 和 `database.grant.create_table` 是目标权限的说明 action，不是操作者的额外准入条件。单独的业务使用权限、`grant.*` grant 或物理 `WITH GRANT OPTION` 均不替代上述五种来源。请求设置 `with_grant_option=true` 时仍按精确对象写入并 readback MatrixOne WGO；撤销使用同一准入和 `data_privilege_version` CAS。

SELECT 授权同时包含目标 Role 在该表上的行列规则配置：`keep` 保留现有规则，`set` 设置或替换，`clear` 删除。目标可以是其他普通 Role 或当前 Role 自身，配置不要求是操作者现有使用范围的子集；只修改目标 Role 在该表上的规则，不修改其他 Role 的规则。

Core 不复制一套平行 Table 数据权限。普通 Role 的 SQL Editor、Worker 和 runtime 必须先让 Core 验证唯一 Effective Role，再由 MatrixOne DCL 事实决定 DDL/DML；`admin`/`superadmin` 对应的 MatrixOne Role 在 workspace bootstrap 时已获得完整产品数据面权限。Database 的创建授权以 Catalog 为父 scope，该范围只约束 MOI 创建入口。MatrixOne 的 `CREATE DATABASE` 为账号级权限；指定 Catalog 和 `all` 建库授权均向对应 MO Role 同步该权限。SQL 直连和 SQL Editor 可以在当前 MO Account 内建库，无需满足 MOI 的 Catalog 范围。

### 5.5 MOI 与 MatrixOne 创建权限对齐边界

MOI 的创建入口先按产品资源层级裁决，再用当前有效 Role 执行 MatrixOne DDL。Database 创建明确区分 MOI 的父 Catalog 范围与 MatrixOne 的账号级权限：

1. `database.create`（已发布别名 `catalog.create_database`）授权指定 Catalog 内创建任意 Database，也允许明确的 `all`。MOI API 必须先对可信父 Catalog 执行 Core Authorize；授权 Catalog A 不允许通过 MOI 在 Catalog B 建库。任一有效建库策略都会向该 MO Role 同步账号级 `CREATE DATABASE`，因此 SQL 直连与 SQL Editor 允许在当前 MO Account 内建库，不应用 Catalog 范围限制。物理 DDL 使用当前唯一 `VerifiedEffectiveRoleID` 对应的连接，MOI Database Ownership 登记同一 Role，保持物理与应用 Owner 一致。策略校验不修改 DCL；只要仍保留建库策略就保留账号级建库能力，移除最后一条后回收。旧 action 与当前 action 使用同一投影规则。`admin`/`superadmin` 的既有系统权限不参与普通 Role 的回收判断。
2. `database.create_table` 绑定父 Database，是普通 Role 的 Table 创建唯一权限项；它直接对应 MatrixOne 的 `CREATE TABLE ON DATABASE <db>`。物理 DDL 使用当前已验证的 Effective Role，随后以同一 Role 登记 Table Ownership；该 Role 通过 SQL 连接获得的建表行为与 MOI 入口保持一致，并继续受 MatrixOne DCL 约束。`admin`/`superadmin` 在 MOI 侧直接通过，其对应 MO Role 的完整权限由 workspace bootstrap 提供。
3. Volume、Folder、File 等没有对应 MatrixOne Database/Table 对象的 MOI-only 创建，只执行自身的 Application IAM 与 Ownership/lifecycle 注册，不产生 MatrixOne 数据权限。
4. Metadata discovery 会把物理层发现、但尚未登记 Catalog 的 Database 自动投影到工作区默认 Catalog；已有 MOI Catalog 登记的 Database 保留原 Catalog 归属。该投影只同步可见的物理 Database/Table 元数据，不凭空创建 `catalog.create_database` 授权或 Ownership 事实；系统数据库仍由 `InternalDBs` 过滤，不进入用户 Catalog。

上述规则只解决“MOI 创建入口与 MatrixOne 真实对象 Ownership/DDL”的边界对齐，不把 Application Policy 变成第二套 MatrixOne DCL，也不允许通过 system credential 绕过 Core 的父 scope 授权。

删除 Catalog 清理最后一条建库授权时，IAM 必须先持久化建库权限投影的恢复 intent，再通过独立连接撤销 DCL。Catalog、Policy、Ownership 和审计仍共用原 tenant transaction。事务回滚后立即尝试恢复；提交结果未知或进程中断则由现有 Saga 执行器和 IAM 恢复调度继续处理。恢复持有目标 Role 行锁，按当前已提交的 Policy/lifecycle 同步并读回 DCL，不能依据删除前快照无条件重新 GRANT，也不能重做 Catalog 删除或复活已删除的 Role。原删除 request/operation 与目标 Role 确定恢复身份，执行锁、重试预算和终态由 Saga 维护。

SQL Editor 是该 MatrixOne SQL 连接串的 Web 版本，不是 Catalog Table metadata API。它的 `/meta/*`、
HTTP SQL 与 WebSocket SQL 仅通过 Core 取得连接，之后直通 MatrixOne：`SHOW`、角色切换、DCL、
规则 DDL 和普通 SQL 的可见性、执行成功或失败均以 MatrixOne 为准。Backend 不追加 Catalog
`table.query` 过滤、SQL 语句拦截或每语句 Role 重验证；Catalog `/catalog/.../table` 也按同一
MatrixOne `SELECT` 事实执行 stable Table ID 过滤，两条入口不得维护独立的读取权限。

Database/Table DCL 与 row/column rule 是不同发布能力。row/column 编辑和 apply 只有在 Permission Schema 同时声明 `row_column_contract_ready`、`row_column_rule_schema_included` 和 live probe 产生的 `row_column_enforcement_verified` 时才可用；probe 失败时 Schema 必须标记不可编辑，Core apply 同样 fail closed。`expression` 中可用 `@标签名` 引用当前执行用户的标签，包含空格的名字使用 ``@`标签名` ``。Core 保存原始表达式并同步 MatrixOne 规则，仅为 MO 不接受的 Unicode 裸变量名补充标识符引号，不替换具体用户值；其他 SQL 语法、函数及引用权限仍由 MatrixOne 校验。

用户标签取值以 tenant `tag`/`user_tag` 的当前 canonical 用户数据为准，每个标签是一个字符串值；不隐式拆分逗号或转换成多值集合。历史记录中的 `tag_value=NULL` 沿用已有标签读取语义，绑定为空字符串，与显式空字符串等价；不能因此阻断连接，也不能当作缺少该标签。Core 在验证 Effective Role 后读取标签，将全部标签合并为单条会话初始化 `SET` 赋值。标签名称遵循 MO 用户变量的大小写不敏感语义，同一用户存在同名变量冲突时拒绝签发连接。缺失或删除的标签不赋值，在新会话引用时由 MO 返回未定义变量错误；标签改名后需更新引用旧名称的规则。普通比较输入仍按字面量处理，标签引用放在 `expression` 中。

该能力在 Core 签发连接或获取内部受控连接时重新读取标签，标签变化时淘汰旧的缓存连接配置；已开始的查询/任务保留本次读取的快照。SQL Editor 已打开的 WebSocket 会话需重新连接（例如刷新页面）才使用新标签，同一会话内的下一条 SQL 不自动刷新。原生 SQL 直连、主动 `SET @变量`、以及自行长期复用已签发连接资料的行为由调用者负责，本期不新增 MatrixOne 内核的受保护变量权限。

Data Privilege mutation 使用独立 version CAS 和 request ID 幂等，不写 Application Policy Store。operation 状态、MatrixOne-first recovery、session 生效范围和 drift readback 以[存储、生命周期与审计](04-storage-lifecycle-audit.md#6-data-privilege-durable-operation)为准，公开 DTO 以[公开 API、前端与 SDK 合同](07-public-api-frontend-sdk-contracts.md#7-data-privilege)为准。

## 6. Data Task、Export Task 与 Semantic Model

### 6.1 Data Task

稳定 ID 为 Backend data task ID；runs/files 等记录从属于 task。

`GET /task/stats` 按 `data_task.read` 的同一集合范围统计业务行，过滤在状态聚合前生效；空范围返回四项零计数。统计不读取任务详情、运行摘要或目标数据树，不因目标 Table/Volume 的读取权限改变任务计数。

任务列表和详情按 `data_task.read` 取得当前页或目标任务后，按任务持久化的可信引用，在当前工作区内批量解析目标资源的 ID、名称和层级路径。这些必要展示元信息属于任务读取结果，不要求查看者另有目标 Volume 的 `volume.read`，也不授予目标资源的访问能力。实际进入 Volume、浏览文件或读写数据时，仍由目标资源的正式入口独立鉴权。未配置 Volume 的任务继续合法；目标卷已删除或不存在时，保留该任务的 `TARGET_PATH_RESOURCE_NOT_FOUND` 展示状态，不以缺失目标阻断其它任务；元信息依赖读取故障仍返回错误。

| Action              | 授权层级          | 业务功能/API 分类                      |
| ------------------- | ----------------- | -------------------------------------- |
| `data_task.create`  | workspace         | 创建导入/同步任务、local upload create |
| `data_task.read`    | object/collection | list/stats/get/files/runs              |
| `data_task.update`  | object            | 修改任务与依赖配置                     |
| `data_task.delete`  | object            | 删除任务及 lifecycle cleanup           |
| `data_task.operate` | object            | pause/resume/retry                     |

create/update/operate 不能用 task action 覆盖依赖；BFF 入口按真实配置完成 `connector.use` 等产品业务 action，实际 `volume.read/write`、`table.query` 和 MatrixOne DDL/DML 仍由数据边界裁决。Mowl 内部 Data Task WorkItem 不重复业务 PEP；DB import 在打开 MatrixOne 连接时使用冻结且已验证的 Effective Role。

Structured Load 新建业务表由 Java Worker 执行 DDL。Core 在准备目标时从持久化 run、snapshot 和 Workflow execution 恢复创建主体及冻结 Role，重新验证 `database.create_table`，通过 Workspace 的用户连接入口签发建表连接。Worker 只执行该连接的可信 session 初始化与建表 SQL，不选择角色，也不在缺少建表连接时改用内部管理连接。checkpoint、fence、commit evidence 和 Kafka raw 表继续使用原内部协议连接。

建表成功后，Catalog 的 `RegisterCreatedTable` 核验物理表属于同一 Active Role，复用 discovery 的数据库元数据锁，原子登记目标 Table 元数据和该 Role 的 Ownership。原任务的登记 request/trace 在重试中保持不变；同名但属于其他 Role 的表不能被认领。物理表已创建而登记失败时保留原表，由现有准备重试校验 schema 并继续登记。run 已有 canonical Table ID 时按已有表访问合同复用，不重新创建或转移 Ownership；这也适用于升级前已成功绑定的周期任务。

文件导入的 Workflow 终态通过原生 `external:import-reconcile` 进入 Connector 正式生成边界，按原执行持久化的主体与 Effective Role 检查 `data_task.operate` 及已有的 Connector/Volume 依赖，与显式导入恢复使用同一合同。恢复只读取原执行与已提交结果并收敛原 run，不重跑导入、不借用回调或调度器身份。Workflow 的终态与收尾确认分开持久化；收尾未确认的终态执行由现有协调器重试，包括详情读取先写入终态与进程中断的情况，不扫描各租户任务。

Doris LocalFS 中转文件是 Structured Load run 的内部从属记录，不是用户 File 或 Volume placement。`POST /api/v1/system/structured-load/runtime:upload-staging-file` 与 `:download-staging-file` 沿用现有 system runtime transport，要求已有 API middleware 验证的 raw system 身份，不接受 delegated browser execution 或普通用户凭据；仅接受 owner 持久化的 workspace、user、task、run、snapshot、workflow execution、Mowl task 和 case 一致的 Doris 运行上下文，不接受用户文件 ID 或任意路径。上传还要求任务 active、run running/reconciling。文件内容只通过既有 FileService 存取，不进入普通文件表、目录、列表、搜索或 orphan-file 回收；读取必须匹配完整提交记录的大小和 SHA-256。此入口不替代源 Connector 或目标 Table 的运行期授权，也不签发新的文件 capability。

### 6.2 Export Task

稳定 ID 为 Backend export task ID；state、files 和 retry attempt 从属于 task。

| Action               | 授权层级          | 业务功能/API 分类                                                       |
| -------------------- | ----------------- | ----------------------------------------------------------------------- |
| `export_task.create` | workspace         | 创建导出任务和外部 MO 目标配置准备                                      |
| `export_task.read`   | object/collection | list/stats/info/state/files                                             |
| `export_task.delete` | object            | 删除任务与允许清理的 task-owned 产物                                    |
| `export_task.retry`  | object            | 用户发起的 rerun/retry 入口重新鉴权；内部自动 retry 延续原 Task context |

list 和 stats 复用同一 `export_task.read` 可见集合及业务生命周期过滤；list 在搜索、排序和分页前过滤，stats 仅聚合可见任务状态，不加载任务文件或来源明细，也不受列表筛选影响。

当前文件源要求 canonical root `volume.read`，目标 Connector 要求 `connector.use`。processed-volume-files 使用 `volume.read`。任务 allow 不代替外部目标、源 Table 或运行期 MatrixOne 权限。

### 6.3 Finetune Job

稳定 ID 为 finetune service 的 `job_id`；metric / log 从属于 job。本资源仅覆盖精调训练节点控制面；推理部署、评测与 `model_backend` 发布不在本资源动作内。

| Action | 授权层级 | 业务功能/API 分类 |
| --- | --- | --- |
| `finetune_job.create` | workspace | 创建训练任务并冻结 train/holdout `run_id`；`Launch` 复用该 action 拉取 Catalog `astra_trace` 并调度训练 |
| `finetune_job.read` | object/collection | get/list 任务状态、产物 URL、指标与日志；native `moi:finetune.run` 编排复用 read |
| `finetune_job.cancel` | object | 取消未终态训练任务 |

v1 demo 可用工作区管理员最大权限行使上述动作。`Launch` 以创建者 actor 会话只读 `astra_trace`。训练编排 native WorkItem 与 Complete/Fail 走 platform / native_workitem boundary，不新增产品 action。成功产物为 `adapter_uri`。

### 6.4 Semantic Model

会话内 `moi-cli` 的知识库创建、来源追加、本地文件上传和 model/source/job 查询使用现有 active-task 身份入口：先验证账号、短期 RuntimeGrant、任务与 manifest、当前 Agent use，恢复冻结的唯一 Role 候选，再进入 Knowledge 的正式生成服务边界。创建继续要求 `semantic_model.create`；追加来源继续要求 Model 的 `semantic_model.update` 和源数据依赖授权；读取继续要求 `semantic_model.read` 并在分页前过滤。RuntimeGrant 不授予这些 action，不允许切换 workspace、Role 或使用 system principal；未接入该身份的知识库操作继续拒绝 runtime proof。

稳定 ID 为 semantic model service 的 model ID；source、document relation、segment、entry、version 和 source job 从属于 Model。

| Action | 授权层级 | 业务功能/API 分类 |
| --- | --- | --- |
| `semantic_model.create` | workspace | create/create-empty/create-with-sources/local upload/source selection preview |
| `semantic_model.read` | object/collection | list/get、绑定智能体反查、sources、documents、segments、entries、jobs、export |
| `semantic_model.update` | object | model/source/governance/segment/entry/version mutation |
| `semantic_model.delete` | object | 删除 Model 或其从属内容 |
| `semantic_model.use` | object | validate、re-embedding、reconcile、import（含 dry_run 预览）、问答或运行期使用、`POST /newmoi/drawings/search`（form `knowledge_base_id`） |

沙箱知识库问答通过 `/newmoi/semantic-models/runtime/{operation}` 接入，操作集合为 find-files、search、read-document、search-document、search-images、read-evidence、describe-tables、query、cite。该调用面要求有效任务子凭据和当前产品身份，复用现有运行时 gateway 的冻结 binding、当前 `semantic_model.use`、资料生命周期、SQL 数据权限及引用校验；它不接受客户端提交 task、Role 或 workspace 替代值。已有知识库管理接口保持普通产品认证合同。CLI 结果文件属于任务工作目录，下载成功不替代独立证据读取与引用校验。

知识库 SQL 工具对 MatrixOne 明确拒绝访问的业务表按当前不可用来源处理：schema 描述省略该表，继续返回其它可读表；查询返回 `available:false`，引导使用其它可用来源，不返回行数据或 SQL 证据制品。拒绝原因保留在受控结构化日志，不向问答暴露无权限表的结构或原始权限错误。该处理不授予数据权限，也不把连接认证、依赖故障或普通 SQL 错误转换为空结果。

本地完整片段分析后的读取登记复用 `read-evidence`：客户端提交精确片段身份和正文摘要，owner 核对本任务持久化证据后记录读取回执。摘要不是 IAM capability，不能读取其它任务或扩大知识库 scope；未核对的本地文件不能成为已读事实。原分页读取和数据侧工具继续沿用原合同。

读取已持久化的 source document 跟随 `semantic_model.read`；新增/变更外部 source 时还要校验 canonical Volume/Table。 Catalog 文件来源已指定 `volume_id` 时，Knowledge 通过 Catalog 验证该文件在当前 workspace 中的精确挂载关系，并对该挂载的 canonical Root 执行 `volume.read`；来源持久化与后续复制使用同一挂载，不能改选较新的其它挂载。未指定 Volume 的旧输入保留唯一 Root 解析，多 Root 无法消歧时拒绝；错误的显式挂载不能退回文件全局解析。Volume 文件选择器遵循相同合同。成果添加知识库的目标选择仅消费知识库列表按需返回的 `can_append_sources` 展示事实。该事实由 Knowledge Service 对已列出的精确 Model ID 经 Core 同时校验 `semantic_model.use` 与 `semantic_model.update` 后给出；缺失或校验失败时前端不可选。它不替代提交时对目标 Model 和来源文件的重新授权。处理任务内部 WorkItem 不鉴权；访问父 Semantic Model、Compute Resource 或受保护源数据服务时，接收方使用 actor、workspace 和 frozen Effective Role 分别重验其 action。Model Backend 只属于管理控制面，内部模型路由不注册 `model_backend.use`。

知识库列表和详情可返回 `allowed_actions`，由既有 generated Service projection 按当前 Effective Role 和精确 Model ID 计算 `semantic_model.update`、`semantic_model.delete`、`semantic_model.use`。详情读取成功后，新增、编辑、删除和导出入口正常展示；实际写操作仍按对应 action 重新鉴权，不能根据按钮可见性放行。导入、追加来源以及自动任务收尾仍要求明确的 update 与 use 投影结果。

知识库详情的 `GetModel` 先独立完成资源读取授权与读取。其后单独计算的动作提示不参与该读取的授权证明：若该计算返回鉴权拒绝或授权依赖不可用，详情保留已获准读取的内容，省略 `allowed_actions` 和 `can_write`，表示提示不可用；不得伪造 allow 或以空数组冒充已算出的 deny。生成 Service boundary 记录 request/trace ID 与完整错误原因。读取本身被拒绝或失败、DTO 事实错误仍按原错误合同返回。本条仅适用于该独立详情提示，不适用于共享 OwnerAccessPlan 的 read scope/final fence，也不改变列表完整性与 mutation 鉴权。

语义模型导出由 BFF 对目标 Model 执行 `semantic_model.read`。Catalog 对认证中间件已确认的 BFF/内部 system transport 不重复执行产品 PDP，也不要求可选 execution contract；普通用户 API Key 直接访问 Catalog 导出接口时，仍须对该 Model 执行 `semantic_model.read`，不能把用户认证等同于可信内部来源。Agent runtime 的知识库绑定只限制目标范围，不替代普通用户路径的资源授权。

知识库创建同时要求 workspace `semantic_model.create` 和关联数据库所在 Catalog 的 `database.create`。默认创建由 owner 从 reservation 解析 `default` Catalog，Catalog 初始化入口通过生成边界对该精确 Catalog 调用 Core PDP；缺少建库权限时返回 `ErrKnowledgeBaseDatabaseCreateDenied`，中文提示为“创建知识库会同步在default目录创建一个关联数据库，您没有此目录的数据库创建权限所以无法创建知识库，如有疑问请联系管理员为您添加权限”。鉴权依赖故障保留系统错误分类，不能误报为缺少权限。拒绝时模型、数据域和 Ownership 的同一事务回滚，不留下半创建知识库。显式目标 Catalog 继续使用普通 Catalog 建库和 Volume 创建边界。`semantic_model.create` 本身不物化 MatrixOne `CREATE DATABASE`；该物理权限只由 Catalog 建库授权投影。

默认知识库初始 provisioning 仍由平台编排，初始根 Volume 无需另授 `volume.create`。MatrixOne DDL 使用已验证并冻结的 Effective Role，Database/Volume Ownership 同样登记给该 Role，资源不归 system Role。后续 Database/Volume/File/Table 访问继续按数据树 action 鉴权；追加来源、修复以及普通 Catalog/Database/Volume 创建不进入初始 Volume 编排例外。

初始 Database 与 `raw_document`、`processed` 两个根 Volume 由 Catalog 的同一初始化操作返回可信资源 ID，生成代理在当前事务中统一批量登记 Ownership。三项资源使用同一个冻结的 Verified Effective Role，但各自保留独立的幂等收据和审计记录；后续数据树操作仍逐项鉴权。

知识库删除按目标是否存在区分终态。目标 Model 已不存在时，删除入口先经 generated boundary 的 `semantic_model.delete.preflight` 完成当前成员与 Effective Role 校验，确认缺失后以 `deleted:true` 幂等成功结束：不执行清理、不登记删除、不改变任何资源状态，该成功不证明调用方持有 `semantic_model.delete`。目标存在时保持原合同：`semantic_model.delete` 与关联 Workflow/Volume/Database 的 delete 全部获准才进入清理，任一缺失整体拒绝且无部分删除。preflight 之后、Prepare 事实读取时目标被并发删除的，由 owner 同一哨兵错误识别并同样幂等收尾；清理、依赖或存储故障永不匹配该哨兵，仍按原错误合同拒绝。

## 7. Model Backend、Agent、Sandbox、Runner 与 Workbook

### 7.1 Model Backend

LLM、Embedding、Parser 共用 `model_backend`。租户创建的 Backend canonical ID 为 owner service 派生的 `llm:<id>`、`embedding:<id>`、`parser:<id>`；部署管理的系统默认 Backend 使用独立的 `llm:moi-managed:<synthetic-id>` 命名空间，且只能从受信任的 `moi_managed` 路由来源派生。endpoint 和 model record 从属于 Backend。

| Action | 授权层级 | 业务功能/API 分类 |
| --- | --- | --- |
| `model_backend.create` | workspace | Backend create/setup |
| `model_backend.read` | object/collection | Backend list/get、endpoint list、LLM/Embedding/Parser model list |
| `model_backend.update` | object | Backend 配置、endpoint create/status、model 配置 |
| `model_backend.delete` | object | 删除 Backend，owner service 引用冲突返回稳定错误 |
`model_backend` 只表示 BFF 模型管理控制面的对象权限；不注册 `model_backend.use`，也不为模型运行时注册独立 Role 权限。Agent 调用由真实父 Agent 的 `agent.use` 准入并签发 task-scoped RuntimeGrant；独立 Runner/Sandbox CLI 的 External Catalog 属于 transport capability，只重验当前 workspace 成员、Direct Role binding 与 lifecycle，并把唯一 Verified Effective Role 冻结到短期 grant。它不能读取 Backend 配置、endpoint 或 credential，也不能产生 Volume、Workflow 或其它业务对象权限。`/newmoi/models`、`/newmoi/embedding/models` 和 Parser model list 使用同一 `model_backend.read` collection filter。system user、内部 transport credential 或 probe 标记不能成为本地 allow。临时配置 probe 仅在明确登记时 membership-only，不能读取未授权 Backend 配置。

### 7.2 Agent

会话内已验证的 runtime 身份可调用目标 Agent 的 binding 查询和工作区 MCP 导入绑定操作。沿用账号认证、active-task/manifest 校验、冻结 Role 恢复和 live `agent.use` 检查；导入与绑定仍由现有 tool owner 和 Agent 的 `agent.update` 正式生成边界分别裁决。系统 Agent 只修改当前业务 workspace 的 binding overlay，不改共享系统包。当前任务 manifest 不因持久化绑定而扩权，新绑定由后续运行重新准入。

稳定 ID 为当前 tenant 的 `agent_id`。用户 Agent 与系统内置 Agent workspace instance 都使用对象权限。

| Action         | 授权层级          | 业务功能/API 分类                                                   |
| -------------- | ----------------- | ------------------------------------------------------------------- |
| `agent.create` | workspace         | 创建用户 Agent                                                      |
| `agent.read`   | object/collection | list/get、知识库反向关联列表中的智能体可见性、metadata、version、binding、model/setup/policy projection |
| `agent.update` | object            | 修改用户 Agent 或系统内置 Agent workspace instance 配置             |
| `agent.delete` | object            | 删除用户 Agent；系统内置 Agent 不接受业务删除                       |
| `agent.use`    | object            | chat/run/A2A 解析真实 Agent 并创建任务时调用                        |

Agent Builder 的沙箱 CLI 是现有 authoring 的 task-scoped transport。上下文和资源元数据读取按服务端当前编辑模式分别要求 workspace `agent.create` 或准确目标 `agent.update`；任务身份与准入还须满足 [运行期合同](03-request-runtime-contracts.md#32-agent-builder-沙箱-cli)。候选目录复用 Skill、Tool、Model Backend 与知识库的正式权限过滤，不扩大当前 Agent 的执行工具或数据范围。候选提交、连续修订和用户确认复用既有资源及生命周期，不新增 IAM action。

包内 Code Tool artifact/capability 是 Agent version 的从属记录，不新增权限资源。运行期读取及每次派发通过生成的 Agent service 边界执行当前 `agent.use`；持久化 task/manifest 限定 workspace、Agent、版本及允许工具，不能充当权限放行结果。读取后须核对 active 工具、runnable 版本、artifact/capability 关联及内容 digest；Worker 只接收执行 payload，不接收 Role、用户凭据或权限结果。

IM 通道配置复用 Agent owner 的现有身份与生命周期事实入口校验目标 Agent；Agent 目标必须由用户显式选择模型，不从 Agent 定义推断默认模型。创建连接沿用 `agent.use`，编辑连接沿用 `ingress_connection.configure`，不额外要求 `agent.read` 或改变入口权限。事实解析不产生授权决定。

工作区 Astra 包加载通过正式 Agent 创建边界以同一冻结身份提交新 Agent 身份并登记 Ownership。普通包加载、Builder 提交与恢复、Skill Creator 永久绑定的发布都经过 `agent.update`，复用正式运行绑定 owner；只有目标版本为 Runnable 且 exact provider/profile 绑定为 active 时，才在同一 tenant transaction 中更新根配置与默认版本 CAS。注册失败保留待配置版本和此前根配置、默认版本。显式默认版本请求使用同一发布 owner，可注册此前未绑定的版本，不引入启动或运行期 fallback。


不注册重复的 `agent.query` 或宽泛 `agent.manage`。A2A 是底层 transport，不是产品 IAM resource；只有解析出真实 Agent 并创建任务时才执行 `agent.use`。该任务的 `RuntimeGrant` 允许 Catalog Model Gateway 验证冻结模型调用范围；`eph-*`、managed `sbx-*` 与 `runner-*` 的每次 bash 调用还经由 `moi-cli` 将该 grant 作为 task-scoped 请求身份交给 Catalog。显式 Runner 的凭据由对应 Edge 注入 bash 子进程；未选择 Runner 的 eph bash 则由 Catalog 在实际 MCP 调用时重验 active task 和 admission，经 Backend 校验会话 reservation 后通过 OpenShell 环境变量注入同一短期凭据；grant 的 `allowed_tools` 是 MOI manifest scope，不用于描述 Edge 内置工具。Catalog 必须重新验证 active task、当前 admission、认证用户/workspace 一致性，再把其中的 Verified Effective Role 仅作为 Catalog handler 调用 Core 的候选值；它不形成 `model_backend.use`、Volume、Workflow 或其它依赖的 allow。受限轮次的正式文件发布须在冻结的 `runtime_capability_policy` 中显式声明 `managed_artifact_publish=true`；缺省仍拒绝，该能力不替代下述 `agent.use` 或 `volume.write`，具体合同见 [请求与运行期合同](03-request-runtime-contracts.md)。附件通过普通 `moi-cli file download` 入口读取，仍以重新验证的 Effective Role 对文件所属 canonical root Volume 执行 `volume.read`；终产物通过 `moi-cli file upload --publish-artifact` 写入用户可见的 `default/agent_chat_files` 下的所属 Volume。首次创建该 Volume 时，父 Database `database.create_volume` 和新 Volume `volume.write` 校验属于业务成功条件；业务 Volume 与同一 Verified Effective Role 的 Direct Ownership 按统一创建一致性合同共同完成，任一步失败不能报告创建成功。上传只接受 working task，并在读取正文前重新校验 task admission 与 `volume.write`；Catalog 先持久化零引用 FileMetadata 与上传计费事实作为不可变对象的 durable owner，再完成对象和 Catalog placement。中断操作可由相同身份幂等重试，长期未完成的零引用文件由既有 orphan-file collector 收敛。完整文件持久化后追加幂等 task-scoped artifact event；两步都成功才报告交付成功。Artifact 发布失败时命令失败而已完成的 Catalog 文件保留，不做终态后恢复或 terminal 延迟。同一 working task 的重试使用稳定文件和 Artifact 身份。执行器内文件只是 executor-owned 本地副本。独立 Runner/Sandbox CLI 不经过 Agent admission；External Catalog 只重验当前 workspace 成员、Direct Role binding 与 lifecycle，冻结唯一 Verified Effective Role 后签发同类短期 grant，不引入独立模型运行时权限。

Channel instance 是 Agent 的受控运行期依赖：执行集合必须是当前 Agent `channel_instance_ids` 与状态有效且支持目标 Tool 的实例交集，不能扫描或继承其它 Agent 的绑定。首次选择实例会修改当前 Agent binding，因此必须先通过正常 `agent.update` BFF PEP 持久化，再恢复原 Tool Call；恢复时 Catalog 只检查 Agent/实例引用、状态和工具支持等业务完整性，不重新执行用户权限判断。选择实例不授予用户对实例的新权限，凭证解析由凭证 owner 校验 workspace、绑定与凭据生命周期。

Agent 永久删除在原 tenant 事务内记录其会话工作目录的清理目标；事务回滚不关闭快照。后台只消费该已提交删除记录，通过 Sandbox 的平台边界关闭对应私有快照并交给既有清理循环，不读取或授予业务资源权限。整个 workspace 删除时，在原 system 删除事务中同时关闭其快照行，回滚不关闭；后台清理不依赖已被删除的 tenant。可恢复的会话归档不触发关闭。Agent ID 重新创建不能清除旧会话的未完成清理记录。

#### Agent 自动化任务与运行记录

现有 `agent-automation-tasks`、`agent-automation-runs` API 由 Agent 自动化 owner 管理；
任务 ID、运行 ID、workspace 和目标 Agent 引用从该 owner 的持久记录解析。当前不注册独立的
自动化 resource/action 或 Ownership，沿用现有生成 Service 的操作合同，不以会话 CLI 接入
为由新增 membership-only 旁路：

- 任务 create/list/get/update/archive 与运行 list/get/result/events 使用现有
  `minimum_access_class=regular` 准入，由统一生成边界验证当前 workspace 身份和 Role。
- 激活任务由原 owner 检查目标 Agent 的可读性、active 状态和可用模型；创建或变更配套
  Workflow 仍经过原 Workflow 正式边界。任务投影中的 Agent summary 仍受 `agent.read` 限制。
- 手动执行通过 `agent_resource.automation_run.create`，由
  `ResolveRunAutomationTaskAuthorizationFacts` 解析目标 Agent，再裁决 `agent.use`；
  调度、回调和执行依赖继续使用各自原有的正式边界，不把管理任务的准入视为依赖授权。
- 普通产品身份和会话 live-task 身份进入同一业务 owner。会话路径只恢复原任务冻结的 Role
  候选，先校验当前任务、manifest、账号和执行 Agent，再执行上述业务准入；跨 workspace、
  已结束任务和受限知识修复 proof 不能借该入口取得一般产品身份。

### 7.2.1 Web Search 与搜索服务配置

Bocha、Tavily、Brave 和 DeepSeek 的搜索执行是 Agent/Automation 的内部工具，沿用调度它的父功能准入，不设独立权限。`web_search_credential` 资源及 `create/read/update/delete/use` action 全部退役，不再出现在 Registry、Permission Schema 或角色编辑器的可授权选项中。

搜索服务的 API Key 配置仍属于 workspace Channel Instance，保留现有配置页面及创建、查看、修改、删除、测试接口，当前按有效 workspace Role 准入。配置管理将来单独设计权限模型与命名，不沿用 `web_search_credential`。

已有策略中的这组授权不再参与运行期决策；与其它有效授权同时存在时不阻断后者。角色显式保存时沿用退役权限清理流程；只打开或取消编辑不改写策略，保存失败的补偿仍恢复原始快照。其它历史未知 action 同样按第 3 节的当前 Registry 投影规则处理；新输入仍须通过当前 Schema 校验。

内部搜索使用通用 Channel 凭据解析。父功能 admission、workspace 一致性、当前 Agent 的实例选择规则、Tool/provider 匹配、connection active 和凭据未过期仍必须成立。connection test 仅记录该凭据版本最近一次外部探测状态，不是运行期的前置条件。显式指定 provider 或使用供应商专属工具时，外部 provider 失败不切换到其它 Channel 或平台搜索；未指定 provider 的通用搜索在同一调用内对可降级失败按候选链自动降级（见下段）。API Key 不得明文 JSON 落库，响应、log 和 Agent state 不得回显 Key。配置 PATCH 必须携带 `expected_version`，最终 SQL 按 version 条件更新；connection test 提交还要锁住被测 `credential_ref`。

Web Search 的实例选择是上一节通用 Channel 绑定交集规则的特定例外：仍限于本轮签名 manifest 的工具集合与当前 workspace；Agent 对某 provider 已配置绑定时，只能使用绑定内实例，显式空绑定排除该 provider；未配置绑定时，可以选择当前 workspace 中唯一 active 且支持目标 Tool 的实例。用户显式指定 provider 与自动选源使用同一实例范围；同 provider 多实例时必须明确选择范围内的 `channel_instance_id`，不随机取 Key。通用搜索未指定来源时按 Bocha、Tavily、Brave、DeepSeek 检查配置；平台服务仅在显式配置且通用搜索工具可用时作为链尾候选，均未配置可选实例时平台服务是唯一来源，未配置平台服务时不产生伪尝试。选源不读取候选凭据；每次实际尝试仍由凭据 owner 临场校验当前实例与凭据，凭据缺失、失效或读取失败均直接失败，不解释为“未配置”而换源，也不触发降级。自动模式下，当前来源返回超时、限流、配额耗尽、服务不可用、供应商侧认证/权限拒绝或通用 provider 失败时，在同一调用内按候选链降级到下一来源，最终结果的工具、来源与 provider 元数据与实际成功来源一致；空结果、非法请求/响应不降级。所有来源均失败时保留最后一次实际尝试的错误码，并附不含凭据与原始响应体的 attempts 摘要；整个降级链共享同一个总超时预算。该例外不改变其它 Channel 的绑定要求，也不授予搜索配置管理权限。

DeepSeek workspace 渠道的 Search 与 Fetch 共享该实例凭据和选择规则，分别通过 `moi_deepseek_web_search` 与 `moi_deepseek_web_open` 调用。通用搜索可显式指定 `provider=deepseek`；既有 `moi_web_open` 继续使用平台源，不自动切换到 workspace 凭据。

### 7.2.2 Agent Plugin

平台插件目录项、个人安装和个人连接是三个独立对象。每个插件身份在目录中只有一个当前包，不提供版本选择；不可变包摘要和安装修订号仅用于完整性校验、并发控制与运行期快照，不是用户可选的版本。`plugin_release` 的内部稳定 ID 为目录包确定的 `pr_<digest>`，`plugin_installation` 的稳定 ID 由安装 owner 分配；`plugin_connection` 使用既有 Agent Connection 的稳定 ID，仅适用于由插件连接入口创建的 Connection。各对象的可信 workspace 与 ID 均由 Catalog owner 按数据库事实解析，包名、外部账号、模型文本和前端状态不是授权资源。Connection 的密钥和授权尝试从属于 Connection，不另立 IAM 对象。

| Action | 授权层级 | 业务功能/API 分类 |
| --- | --- | --- |
| `plugin_release.read` | object/collection | 当前目录检索、推荐、包详情及安装前取得包摘要；列表在分页前应用 Core filter |
| `plugin_installation.create` | workspace | 为当前用户安装插件并首次绑定个人连接；同一用户在同一 workspace 不重复安装同一插件 |
| `plugin_installation.read` | object/collection | 安装列表/详情、能力摘要与连接准备状态 |
| `plugin_installation.update` | object | 更新当前包及连接与执行宿主绑定；使用内部修订号 CAS |
| `plugin_installation.delete` | object | 卸载；不删除可复用的 Connection 或包 |
| `plugin_installation.use` | object/collection | 将当前用户的安装纳入任一 Agent task 的能力快照，并在每次调用前校验安装记录与绑定 |
| `plugin_connection.create` | workspace | 创建插件使用的外部账号或服务连接 |
| `plugin_connection.read` | object/collection | 连接列表/详情、状态和授权结果；不返回密钥 |
| `plugin_connection.update` | object | 发起授权、轮换凭据、选择账号或宿主、禁用和断开 |
| `plugin_connection.delete` | object | 删除连接及其密文、未完成授权尝试；被安装引用时返回冲突 |
| `plugin_connection.use` | object | 在绑定、Agent task 准入与每次实际取得身份材料前独立授权 |

`installation.create`、`connection.create` 在当前 workspace 授权，均可沿有效 Role graph 继承。安装、连接创建成功后，当前 Verified Effective Role 登记为对应对象的 Direct Owner。对象更新、删除和使用授权到可信的 exact ID，`read` 与 `use` 不隐含 `update`；安装与连接的 restricted collection 在 storage 层先过滤 ID、owner 用户以及连接的有效状态，再计算 total/分页。安装记录存在即为已安装，卸载删除该记录。安装和插件连接只供 owner 用户使用，该用户在同一 workspace 的所有智能体无需逐个绑定；其它用户、跨 workspace 的 Release/Connection、与组件声明不匹配的 auth profile 或宿主均 fail closed。

Agent 运行从真实 Agent 的 `agent.use` 准入开始；每个纳入 task 的插件安装再要求 `plugin_installation.use`，每个实际使用的外部账号再要求 `plugin_connection.use`。任务快照固定包摘要、安装修订号、Connection ID/授权代次和组件，不能把新增权限灌入旧 run。显式选择 User Runner 时，命令与 stdio 插件在同一个 task 固定的 Runner 上运行，每次发送前由运行期 PEP 对该 Runner 重验 `agent_runner.use`；短期身份、已加载描述和连接代次均不是 durable allow。内部 relay 只解析 canonical Runner 的当前工作区、有效状态与 Edge owner，并传递端到端密文，不计算业务权限、暴露工具或转发到另一个执行器。每次调用重验对象有效状态、当前授权与出站目标；安装或连接的 `use` 不授予 GitHub 仓库以外的 MOI Catalog 数据对象权限。用户完成安装/授权后必须经新请求重新验明当前 Effective Role，才能为同一 task 建立 successor run。
### 7.2.3 Agent Team 与 IngressConnection

`agent_team` 是显式、用户归属的 MOI 应用对象；成员表是 Team 候选 Agent 的唯一事实来源，不能从 Agent 的 Channel binding 反推 Team。稳定 ID 为 `agent_teams.id`，父资源为 workspace；创建使用 workspace 父资源，成功后以本次 Verified Effective Role 注册 Team Ownership。成员和 Team Session 是 Team 的内部事实；外部双向通信连接与外部对话映射归 `ingress_connection`，可以指向 Agent 或 Team。

| Action | 授权层级 | 业务功能/API 分类 |
| --- | --- | --- |
| `agent_team.create` | workspace | 创建 Team 与初始成员 |
| `agent_team.read` | object/collection | 获取、列表、成员/Session/收发记录读取 |
| `agent_team.update` | object | 修改 Team、成员和 Team Session |
| `agent_team.delete` | object | 删除 Team 并撤销全部入口关联 |

Team 创建、Ownership 和初始成员必须在同一租户事务完成。删除时，Team 状态、全部 IngressConnection、Managed Credential 及 Team 与连接的 Ownership 在同一租户事务完成清理；任一步失败必须返回错误并回滚整次删除，不报告部分成功。列表必须先使用 `agent_team.read` 的 ResourceAccessFilter，再计算 total 与分页。业务 owner 另存 `owner_user_id`，但它不是授权替代品：管理请求仍要求 Core 确认的 action；关联入口另校验 Channel 与 Team 的 workspace、归属用户一致。

`ingress_connection` 是一个外部 Bot、App 或邮箱到唯一 `TargetRef(kind, workspace_id, id)` 的独立受控连接，稳定 ID 为 `ingress_connections.id`。Callback 和邮件连接引用已授权的 ChannelInstance；Managed Stream 连接直接引用 Credential Store，不创建 ChannelInstance。创建连接使用目标已有的 `agent.use` 或 `agent_team.update` 决策，并在校验相应来源依赖后，以同一 Verified Effective Role 登记 `ingress_connection/<connection_id>` Ownership，不增加第二次等价授权。

| Action | 授权层级 | 业务功能/API 分类 |
| --- | --- | --- |
| `ingress_connection.configure` | object | 更新、启停、验证或删除连接 |
| `ingress_connection.read` | object/collection | 读取连接配置及收发投影；collection 必须先做 ResourceAccessFilter |

新建企业微信连接的扫码绑定与创建连接使用同一目标准入（`agent.use` / `agent_team.update`）。扫码会话只在五分钟内、对发起用户、workspace 和原 TargetRef 有效；查询结果每次重新经过相同生成边界。扫码不创建 MOI 连接或 Ownership，也不启动 receiver；收到凭据后仍经原创建连接入口持久化。扫码凭据不得进入日志或浏览器持久存储。

平台验签只证明消息来自平台；Managed Receiver 只接受已经完成平台鉴权的连接。执行身份由配置时保存的可信接入用户与运行期合同提供，外部发言人不能覆盖。普通输入冻结 TargetRef、association_version、config_version、execution context 与 ReplyRoute；关联变化后尚未提交的输入终结为 `channel_target_changed`，已提交任务保持原事实。直接 Agent 复用现有 Runtime Conversation，Team 使用 Team Session；两者都在各自 Session owner 中完成持久 admission。Runtime 对本轮实际 Agent 执行 canonical `agent.use`。回复由冻结 ReplyRoute 对应的 Transport 发送到原群、私聊、线程或邮件往来。连接权限不授予读取 Channel 或 Managed Receiver secret，也不把 Team Membership 扩展为 Agent 的 Channel 工具权限。

Callback 和邮件接收由连接 owner 读取 Channel 来源事实（workspace、provider、类型、状态、账号标识、凭据引用及版本），该内部查询属于平台事实边界，不要求外部 provider 或后台轮询携带产品用户身份。凭据 owner 仍校验来源关联并执行 provider 验签；此事实查询不产生产品授权，消息准入与异步执行继续使用冻结的可信接入身份重验目标权限。用户读取、配置和验证连接仍走各自受控入口。

### 7.2.4 Agent Web 应用发布

Web 应用发布记录（system DB `agent_resource_agent_webapps`，主键 `agent_id`）是 Agent 的从属投放记录：一个 Agent 至多一条，新建 Agent 时自动创建（enabled=true + token），存量 Agent 首次查看时 lazy create（enabled=false），生命周期由发布方管理（查看、启停、rotate 公开链接，PRD V1.3.0 无发布/钉版/upgrade 操作）。与 Agent Version 同属 Agent 的从属记录，不新增权限资源：查看复用 `agent.read`（可见状态并复制完整链接），启停与 rotate 复用 `agent.update`，可信资源始终为 agent 作用域。公开链接 token 是不可预测的 32 字节 URL-safe 不透明串，rotate 后旧 token 立即失效；停用不销毁 token，重新启用恢复原链接；Web 应用始终跟随 Agent 当前可对话运行配置，不绑定版本。

发布方查看 Web 应用的会话列表、消息、反馈明细和统计均复用该 Agent 的 `agent.read`，由生成 Service boundary 执行当前 Effective Role 校验；服务端读取限定发布方 workspace、Agent 与 `purpose=webapp`，不按当前登录用户过滤终端用户。会话与反馈是 Agent 的从属运行记录，不新增资源/action，不以公开链接是否停用决定发布方历史可见性。

匿名访客经公开数据面的准入已按 [请求与运行期合同](03-request-runtime-contracts.md) 登记为数据面 capability：公开路由 `POST /api/v1/public/webapp/resolve` 不经产品身份认证，service 校验发布记录存在、`enabled=true` 且 token 恒时匹配后只产生「可访问该 webapp」的入场事实；token 绝不进入权威 identity Context，终端对话的 `agent.use` 业务准入（M3 会话里程碑接入时）始终由发布方 workspace 与冻结身份经唯一 PDP。resolve 失败一律 HTTP 404 防枚举，body code 区分 disabled(16) 与 unavailable(3)；rotate 或停用后旧链接 fail closed。公开路由不新增 canonical resource/action。

### 7.3 Agent Sandbox 与 Runner

Runner 注销先由连接 owner 将关联的原生会话持久化为不可执行的清理状态。令牌过期或离线恢复不续签执行权限：已批准的主机身份可以通过端到端认证加密的清理通道领取已有 `retiring/expiring` 会话、关闭它们并回执。通道不创建清理意图，不开启登录或工具调用，不返回凭证；回执必须匹配 owner 当前的完整会话身份与授权 revision。它是既有已准入操作的幂等完成协议，不是产品资源访问入口。

Sandbox 和 Runner 都是工作区内可授权的执行器对象；稳定 ID 分别由 sandbox 和 runner owner service 分配。创建成功后当前 Verified Effective Role 成为唯一 Direct Owner。

| Action | 授权层级 | 业务功能/API 分类 |
| --- | --- | --- |
| `agent_sandbox.create` | workspace | 创建 managed sandbox 与读取 workspace 实际创建配额，可沿有效 Role graph 继承 |
| `agent_sandbox.read` | object/collection | list/get 与连接投影 |
| `agent_sandbox.update` | object | suspend/resume、network tools 配置 |
| `agent_sandbox.delete` | object | 删除 sandbox 与 edge token 清理 |
| `agent_sandbox.terminal` | object | 签发短期 terminal/SSH session token |
| `agent_sandbox.use` | object/collection | 作为 Agent/Workflow 执行器使用；运行前重验 |
| `agent_runner.create` | workspace | 注册 custom runner，可沿有效 Role graph 继承 |
| `agent_runner.read` | object/collection | list/get 与连接状态 |
| `agent_runner.manage` | object | 刷新 edge registration token |
| `agent_runner.delete` | object | 注销 runner 与 token 清理 |
| `agent_runner.use` | object/collection | 作为 Agent/Workflow 执行器使用；运行前重验 |

既有任务身份入口支持 managed Edge token 与 task proof 的绑定认证：身份 owner 内部完成 UC
认证，重验 working task、真实 Agent 的 `agent.use` 和冻结执行器的 `agent_sandbox.use` / `agent_runner.use`。
不返回 PAT、不重签证明、不新增资源/action；目标文件或数据权限仍由自身 owner 裁决。

`agent_sandbox.*` 仅适用于用户可管理的托管 Sandbox（`sbx-*`）。对话绑定的临时
Sandbox（`eph-*`）不是 IAM application object，不得通过显式 A2A executor 选择进入
`agent_sandbox.use`；Backend 必须在调用 Core PDP 前将其作为用户不可见资源 fail closed。

显式选择 `runner-*` 或 `sbx-*` 时，A2A admission 的 allow 不是长期 capability。Catalog
把 canonical executor、actor 和 Verified Effective Role 绑定进 task-scoped RuntimeGrant，
Astra 仅通过版本化 `edge_ws_authorized` transport 派发，并在每次 live send 前回调 Catalog，
由同一 Core PDP 重新验证 Agent use、当前 Role、executor 的业务 lifecycle 和对应 `*.use`；只有本次
`*.use` 依赖 Owner allow 时才读取 Ownership。
该 transport 不使用离线 durable relay；deny、事实缺失或 Core 不可用时不发送且不切换执行边界。

执行器对象的 allow 不覆盖其访问的 Volume、Table、Model Backend 或其它运行期依赖；每次实际访问由对应 owner 重新授权。

### 7.4 Workbook 与 SQL Editor

Native `POST /query/run` 复用 SQL Editor 的执行服务，在同一响应返回有界结果、
截断标识和影响行数；`/query/execute` 继续返回查询 ID。沙箱调用这些 SQL 和 `/meta/*`
入口时，API 先验证账号及 active-task RuntimeGrant，恢复任务冻结的唯一 Role，
再进入 SQL Editor 的正式生成服务边界与 MatrixOne Active Role 连接。
不新增 SQL action，不从请求或 CLI 配置重新选择默认 Role；普通用户无 runtime proof
的调用保持原合同。未接入 runtime identity 的产品入口拒绝携带该 proof，不能忽略它后
按普通用户默认 Role 执行。

稳定 ID 为 workbook service 的 workbook ID；version 从属于 Workbook。

| Action            | 授权层级          | 业务功能/API 分类                             |
| ----------------- | ----------------- | --------------------------------------------- |
| `workbook.create` | workspace         | 创建 Workbook                                 |
| `workbook.read`   | object/collection | list/detail、version list、读取保存的 SQL     |
| `workbook.update` | object            | metadata、version create/update/save/finalize |
| `workbook.delete` | object            | 删除 Workbook 与从属 version                  |

Workbook 的 create/list/detail/update/delete 和从属 version 接口复用 SQL Editor 的 active-task 身份恢复入口，接受普通产品身份或合法任务凭据。任务凭据仅恢复冻结 Role 并重验任务、manifest 与当前 `agent.use`；Workbook 的当前 action、集合过滤和 Ownership 仍由原正式生成边界校验。无效或终止任务不能创建、读取或修改 Workbook；不能因 CLI 携带合法任务头就在 HTTP 身份层拒绝。

Workbook action 不授予 SQL 涉及的 Database/Table 数据权限。SQL Editor 执行前必须由 Core 建立唯一
Effective Role 的 MatrixOne 连接：显式 candidate 使用 `OpenDBForRole`，缺省 candidate 由 Core
解析 Default Role。建立后 SQL Editor 不解释用户 SQL，保持与该连接串相同的 MatrixOne 执行语义。

### 7.5 Data Dashboard

稳定 ID 为 Catalog owner service 生成的 dashboard ID；Chart 是 Dashboard 的从属记录，不注册独立 IAM resource。Dashboard 保存手写 SQL、Catalog 展示范围和图表配置，但不保存数据源凭证。

| Action | 授权层级 | 业务功能/API 分类 |
| --- | --- | --- |
| `data_dashboard.create` | workspace | 业务对象与 Ownership 按统一创建一致性合同共同完成，任一步失败不能报告成功 |
| `data_dashboard.read` | object/collection | list/detail、读取从属 Chart 与 Catalog scope |
| `data_dashboard.update` | object | 修改 Dashboard metadata、scope，创建/修改/删除从属 Chart |
| `data_dashboard.delete` | object | 删除 Dashboard 与从属 Chart；Ownership 清理与原删除操作共同完成 |
| `data_dashboard.use` | object | preview、生成受持久化 source scope 约束的 SQL 草稿、run 已保存的只读 SQL、从属 Chart drill-through 与结果下载 |

会话 CLI 通过既有 Data Dashboard 产品 HTTP 接口进入同一 owner。HTTP 身份入口同时接受普通产品身份和已验证的 live-task proof；后者只恢复任务冻结的 Role 候选，并重验 working task、manifest、actor/workspace 与当前执行 Agent 的 `agent.use`，不产生 Dashboard 或数据权限。Dashboard/Chart 的 create/read/update/delete/use、集合过滤、Ownership 与调度身份比较仍由原生成边界执行。持久刷新使用原 Chart/Workflow owner 保存的调度主体和 Effective Role，不保存会话凭据；WebSocket 和内部 Worker execution-spec/evaluate-alert 继续各自原认证协议。

`data_dashboard.use` 只授权使用 Dashboard 对象，不授予 SQL 涉及的 Database/Table 数据权限。Dashboard 的公开 point API 由 BFF PEP 对精确 `data_dashboard.*` action/resource 执行一次 Core 裁决；`bff_complete_pep` 可携带真实 canonical facts 供审计，但 Catalog 非数据树 route 无条件信任可信 BFF，不要求或重复校验该合同。`SQLDraft` 只接受精确的 `data_dashboard.use` fact。Dashboard list 没有 point action fact，仍可按过渡约定在 Catalog owner 的存储查询、count 和 pagination 前执行 `data_dashboard.read` `ResourceAccessFilter`。

没有待清理 Chart 的 Dashboard 在一个 Tenant 事务中删除业务记录、source 引用、Ownership 与必需审计；失败整体回滚，不创建 Saga。存在 Chart 时跨越 Tenant、System 与运行文件存储，只保留 Dashboard 原有的一份持久化操作。Workflow owner 先禁用关联 Workflow，确认没有活动执行，再清理调度与运行文件，最后删除 Workflow 元数据及 Ownership；文件清理完成前保留原元数据，重启后仍可定位未完成清理，不再创建嵌套 Workflow 删除操作。已持久化的旧 Workflow 删除记录继续由原 owner 收尾。

跨库删除未完成时，列表保留 `LifecycleStatus=deleting` 的元数据，提供继续删除入口；详情、编辑和运行仍只接受 active 对象。普通 DELETE 重试由 Dashboard owner 使用已持久化的 lifecycle request ID 定位原 Saga，客户端不必保存旧请求编号。重试仍先执行当前 `data_dashboard.delete` 授权，并以原 payload hash 校验 actor 与 Effective Role 不变；身份变更、原 intent 缺失或生命周期 fence 不匹配时拒绝，不接管或重建旧任务。执行锁、步骤重试和 Ownership 清理复用原 Saga；全部清理完成后才返回成功，已完成删除不重复外部清理。

`execution-spec`/`evaluate-alert` 是共享的已准入 Dashboard 入口：可信 BFF 和内部调用直接进入，Worker 如发送只使用登记的 `data_dashboard_refresh_v1` 元数据，二者都不重新执行 `data_dashboard.use` PDP。runtime continuation 仅用于可信 worker transport 的审计和上下文记录，不要求或伪造 BFF action fact。两种入口都不覆盖数据资源：持久化 source scope 的批量读取可在 Catalog 侧按过渡约定执行 `table.read` filter，preview/run/drill-through 的执行端仍在 Backend 先拒绝非只读 SQL，再复用 SQL Editor 的执行服务，并由 Core 验证的当前 Effective Role 建立 MatrixOne 连接；drill-through 的结果下载必须复用同一次请求的父 Dashboard、Chart 与 Effective Role 边界。数据树 Core/PDP 或连接建立失败时 fail closed。Dashboard scope 只用于编辑器中的 Catalog 浏览范围，不是数据权限边界。

## 8. Data Share

会话 CLI 通过现有 Data Share 产品接口复用 live-task 身份入口：重验 working task、冻结 manifest、actor/workspace 和当前 `agent.use` 后，仅恢复任务冻结的 Role 候选。发布、源表选择、订阅、集合过滤及 Ownership 继续进入原正式生成边界，不将任务 grant 解释为分享权限。发布在当前来源 workspace 执行；接受邀请只在当前目标 workspace 执行，任务身份不能切换到另一 workspace 或 source owner。目标数据读取仍验证 active relation、`catalog.show_databases` 与当前 Effective Role 的 MatrixOne DCL。workspace-name 接口仍只提供原 membership-only 最小投影；system-only 迁移、drift、reconcile 与恢复接口不接受任务身份。

所有 Data Share 发布订阅操作共同遵守[全局控制面 Runbook §0.8](../data-share/moi-data-share-global-cutover.md#08-生命周期)：
创建、修改及 target 调整、删除发布、接受和取消订阅使用同一套持久有限重试、崩溃恢复、终态解锁和新请求接续合同。
`Failed` 是原用户命令的最终结果，释放本任务业务锁但保留外部结果、稳定资源身份和未完成清理事实；
不因操作类型不同、已有部分 MO 副作用或待收尾的 IAM 就要求永久占锁。

未终结任务由统一恢复入口使用原身份和剩余预算，只处理必要步骤；新的合法请求重新鉴权并创建新 Saga，
取资源锁后核对旧未决 DDL 与当前事实，再按本次意图补齐或清理。新删除不先补完旧创建，旧 Failed 回执不变。
这些规则不授予清理旁路：当前鉴权拒绝、真实身份冲突和不可验证的共享关系仍拒绝相应操作或数据访问，
不能为使新请求成功而恢复权限、覆盖 Owner 或把读取失败当成记录缺失。当前实现差距见[实现状态](05-implementation-status.md#data-share-saga-统一合同差距)。

### 8.1 Data Publish

产品 API/IAM resource ID 仍是来源 workspace 下的 publication ID；全局存储主键为
`source_workspace_id + publication_id`。Core 在
`moi_system.data_share_publication` 保存该稳定 ID、源 Database 身份、MatrixOne 物理数据库名、Table
`rel_id` 范围、创建人、备注和管理证明。publication 是否存在、当前表范围和目标账号以 MatrixOne publication
事实为准。全局产品身份行不能单独证明 MatrixOne publication 存在，也不能单独形成 IAM allow。每个新对象仍
在来源 tenant IAM storage 登记当前 Verified Effective Role 为 Direct Owner。

| Action | 授权层级 | 业务功能/API 分类 |
| --- | --- | --- |
| `data_publish.create` | workspace | check-name、create；同时校验来源 Database；selected scope 逐个校验 Table stable ID，all scope 要求 `table.query` 的 `AllResources` plan |
| `data_publish.read` | object/collection | publication list/summary/detail |
| `data_publish.update` | object | 修改发布与目标范围；数据范围变化时按 create 的 selected/all scope 规则重验 Database/Table |
| `data_publish.delete` | object | 删除发布并终止后续订阅访问 |

来源 Table picker 先解析路径中的 stable Database ID 对应的父 Catalog，并执行 `catalog.show_databases` point check，再对 Table 执行
`table.query` collection filter；Core 先读取当前 Effective Role 的 MatrixOne `SELECT` facts，空 facts 返回空集合，
非 `AllResources` 计划只查询允许的 stable Table ID，并在过滤后计算 total 和分页。Backend route、Core canonical
Registry 与生成的 route authorization inventory 必须同时登记
这两个 action，不能用 workspace membership 或 `data_publish.create` 代替。

结构校验先于鉴权但不得泄露资源存在性。Core 不再维护平行的目标关系状态机，也不比较来源/目标
revision；所有 MatrixOne DDL 后必须 exact readback。publication list/summary 以 MOI 全局元数据为记录集合，先由
`ResourceAccessFilter` 过滤候选稳定 ID，再关联 MatrixOne 与 Catalog 事实，最后计算 total 和分页。
MO 对象已不存在但 MOI 清理未完成时，保留可操作的管理记录；不因缺少 MO fact 或展示路径而隐藏。
冲突或无法唯一映射的事实记录 drift，不猜测目标 workspace、Ownership 或对象绑定，也不据此允许共享数据访问；
MatrixOne、Catalog、Core Authorize、业务 transaction 或扫描的真实依赖故障返回 `503`；目标聚合读取中的单个来源故障按[全局控制面 Runbook §0.4](../data-share/moi-data-share-global-cutover.md#04-共享-catalog-与授权粒度)隔离，相关订阅不可读且保留绑定与写保护，不影响独立数据库。已确认的权限拒绝与可控授权异常遵循[失败语义](01-product-authorization-model.md#9-失败语义)，不能统一包装成服务不可用。Ownership 登记/清理失败必须保留既有业务结果、稳定错误和原操作的恢复上下文。

删除 publication 的 MO DDL、目标清理、Ownership 和全局记录清理由同一 Saga 管理，先持久化恢复上下文，
并以已有 mutation lock 阻止并发 accept/update。全部必需清理完成前保留资源定位所需事实；
全局记录删除、Saga 完成与锁释放同事务提交；失败则保留清理事实，按 §0.8 提交失败终态并释放本任务锁，
不能仅写日志、报告成功或无限保持 Running。
删除失败后的新请求仍校验当前 `data_publish.delete`，不要求 MO publication 仍存在；确认对象已删除后，
新 Saga 只执行剩余清理，旧 Failed 保持不变。若角色、Ownership 或单独授权已经清理，新请求按当前权限拒绝；
不恢复或补发权限。已准入的操作继续执行，除数据树原有权限边界外不增加后置检查。列表与新请求准入以
[全局控制面 Runbook §0.8](../data-share/moi-data-share-global-cutover.md#08-生命周期) 为准。

首次删除也不要求 MO 对象仍存在：通过当前删除鉴权后，确认 publication 或订阅 Database 已被外部删除时，
跳过对应 MO 删除并继续清理 MOI 元数据及权限，不恢复共享数据访问；MO 查询故障和同名身份冲突仍返回错误。

### 8.2 Data Subscription

产品 API/IAM resource ID 仍是目标 workspace 下的 subscription ID；全局存储主键为
`target_workspace_id + subscription_id`，关系唯一键为
`target_workspace_id + source_workspace_id + publication_id`。Core 在
`moi_system.data_share_subscription` 只保存稳定产品身份以及已完成的目标 Database 绑定，不重复保存
Table 范围。邀请、MatrixOne subscription Database、订阅时间和状态以 MatrixOne subscription 事实为准。
Invitation 的目标 Database 绑定为空且没有 Database Ownership；接受并完成 MatrixOne DDL 与 Catalog 投影后
Database 绑定与同一 Verified Effective Role 的 Ownership 必须按原持久化操作完整完成；登记失败不能报告订阅成功。
订阅失败后，用户通过正式 PDP 用新请求创建新 Saga；旧 Failed 不恢复。MO 已有同关系订阅库时只补 MOI；IAM 尚未完成则按本次已验证身份重新准备，已有完整成功回执且匹配实际 Database ID 时保留原 Ownership。不得因重新订阅撤销已有策略、覆盖冲突 Owner，或将 IAM 读取失败当作尚未登记。
接受订阅的中断恢复按上述统一合同确认 MO 结果：已建同一库时只补未完成的 Catalog、IAM 和全局绑定；
确认未建库时终止原创建并取消其准备，不在重启时重新建库或新建原任务的 Ownership 准备。结果未知、查询或
清理失败使用剩余预算，耗尽后失败解锁并保留未决事实，不无限占锁。复用已有库且 IAM 准备失败的任务只补偿
本次准备、保留原库；新订阅按本次已验证身份准备，已有完整成功回执仍按实际 Database ID 核验并保留。
撤销后 MatrixOne relation 消失，Database 绑定保留到业务 Saga 清理成功，使 owner service 继续按业务 lifecycle
拒绝残留 Database；Ownership 清理不参与该 fence。MatrixOne 已证明 active 的历史关系不因订阅时间元数据缺失而降级或
跳过。

| Action                     | 授权层级          | 业务功能/API 分类                                                                                 |
| -------------------------- | ----------------- | ------------------------------------------------------------------------------------------------- |
| `data_subscription.create` | workspace         | accept/subscribe；系统解析固定共享 Catalog，不接受调用方选择目标 Catalog                          |
| `data_subscription.read`   | object/collection | subscription list/detail；同一 collection filter 覆盖 `unsubscribed`、`subscribing`、`subscribed` |
| `data_subscription.delete` | object            | unsubscribe/cancel subscription，包含 MO 已删除但 MOI 清理未完成的记录                             |

subscription list 以 MOI 全局元数据为记录集合，统一使用 `data_subscription.read` 并在 count/pagination 前过滤。
MO 已删除但业务清理未完成的记录仍展示并允许有 `data_subscription.delete` 权限的用户重新取消订阅；
按上述 §0.8 的已确认方案创建新 Saga 清理，旧 Failed 不变。管理可见性不代表 active relation 或共享数据读取权限。
`data_subscription.create` 只控制接受邀请，不能扩大列表可见性。workspace-name projection 只返回已确认边界内的稳定 `id/name`，不能作为 publish/subscription allow。

每个新建 active subscription 在 target workspace 的系统共享 Catalog 下对应一个 Database。历史已激活订阅
保留原 Catalog，通过稳定 `database_id` 继续完成查询、删除和取消，重新接受后进入系统共享 Catalog。授权粒度是单个
subscription Database，不是整个共享 Catalog。`data_subscription.read` 只控制订阅管理投影；共享 Database
展示复用 target workspace 现有的 `catalog.show_databases`，并在 Data Share owner 中继续验证 active relation。不能
因此读取同一共享 Catalog 下的其他 subscription Database。共享 Catalog 只是固定最小祖先展示，不形成
collection-wide allow。MOI 权限配置只支持订阅 Database 的整库读取授权：显式提交 `database.query`，
Data Privilege 以目标 Database 稳定 ID 解析库名，并写入、读回 MatrixOne `SELECT ON TABLE <db>.*`。
同一次授权同时物化同库 `SHOW TABLES`，保证当前 Role 能读取表结构；两项均完成才报告整库授权成功，
撤销时一并回收。设置 WGO 时，两项物理权限都必须按同一目标配置写入和 readback，不能只写 SELECT WGO。
Core 将该真实 DCL 事实映射到同库的 Catalog Table；不能要求订阅方存在本地物理 Table 目录行。
整库授权不替代 Database 元数据可见性或 active relation 校验，也不授予其他订阅 Database。
订阅 Database 为只读，不开放 `database.create_table`；不支持在一个 subscription 内按单个 Table 继续拆分 Role。

Role 权限选择器仍展示可见的订阅 Table，但返回 `selectable=false` 和
`SUBSCRIPTION_TABLE_GRANT_UNSUPPORTED`，由前端说明仅支持整库授权，不支持单表授权及行列规则。
Data Privilege 的校验、应用、Role 创建初始化和已有权限项编辑均执行相同限制；不能只依赖前端禁用。
非法配置返回稳定业务拒绝，不因读取不到订阅方的物理列目录而返回 503。
订阅类型以当前租户 MatrixOne `mo_database.dat_type` 为准，覆盖通过原生 SQL 创建的订阅库；
不能通过切换源租户连接或扩大成整库授权来补齐单表权限。
该限制属于 MOI 权限配置范围；SQL Editor 和原生 SQL 仍遵循第 5.5 节的 MatrixOne 直通边界，
本次不新增 SQL 解析或拦截，也不隐式删除用户通过原生 SQL 配置的 DCL/RULE。

Table 数据访问继续由当前 Effective Role 的 MatrixOne DCL 执行。`catalog.show_databases` 只控制产品 Database 元数据，
不能替代 MatrixOne DCL；Table privilege 继续走现有 data-privilege API，不新增 Data Share 专用
DCL 状态或把 Application Policy 伪装成 SQL allow。Table 的 `table.query` 同时是 Catalog 元数据过滤和
MatrixOne `SELECT` 的唯一事实来源，不维护两份门禁。任何 MOI SQL/Task 路径为 subscription Database 调用 `OpenDBForRole` 前，
必须先验证 active relation 和该 Database 父 Catalog 的 `catalog.show_databases`，随后仍由 MatrixOne DCL 决定实际数据访问；通过
MOI 产品入口不能只持有 DCL 而绕过 Application IAM。

Backend workspace 初始化以 workspace owner 的 Catalog 用户身份创建 stored name 为 `shared` 的共享 Catalog；
Core 必须验证 owner 的 direct `superadmin` binding 和 lifecycle，并将该 verified `superadmin` 登记为 Catalog Direct
Owner。MatrixOne `accountadmin` 只执行租户 Database DDL，不作为 MOI Catalog IAM actor。已有 workspace 的幂等 repair
先通过 Core system 只读接口解析权威 owner，再以相同 owner 身份进入正常 Catalog Create/Ownership 链路；不得使用当前
Catalog list/tree 调用者的 `workspace.create_catalog`，也不得使用 process System 绕过 Core PDP。创建后在现有
`catalog_reserved_resource` 中登记通用 `catalog` 保护和 `data_share_catalog` purpose identity；描述单独绑定
`moi_backend.catalog.shared.description`，名称和展示路径固定使用存储名称。reserved identity 使该 Catalog 与 Default 一样禁止
rename/delete；purpose identity 只标识系统容器，不参与 allow/deny，也不保存发布订阅关系。已有未保留的同名普通
Catalog 时，workspace 初始化返回明确冲突且不修改该 Catalog；只能由具备权限的显式迁移或用户操作先处理名称冲突，
不能从 Catalog tree/list 等读路径自动改名或把普通 Catalog 接管为系统 Shared。同名 Catalog 已属于其他系统
reservation、purpose identity 指向缺失对象或出现重复 identity 时同样 fail closed。

Catalog Core 的 `ResolveSharedCatalog` 按唯一 `data_share_catalog` 保留记录解析 Catalog ID，并校验通用 `catalog`
保护和对象存在性；Default 为排除 Shared 后唯一的通用 `catalog` 保留记录。名称翻译映射不参与身份解析。
解析不创建 Catalog，也不接受 Backend 或调用方传入 Catalog ID。共享 Catalog 禁止普通 Database create、rename 和 delete。
普通 Database/Table mutation owner 必须在写入前通过 `target_workspace_id + database_id` 检查任何
未清理的 subscription Database 绑定并拒绝写入；该写保护查询只消费全局 subscription 事实，不能反向产生
allow。

普通 Catalog list 在 count/pagination 前按 `workspace.show_catalogs` 过滤，不得用 System metadata 把 filter 排除的
`shared` 重新注入；Catalog tree 复用 Core 的授权投影，只为可读后代保留最小祖先。Backend Catalog read
adapter 先解析 active subscription Database，再经 Core `catalog.show_databases` filter 动态注入。仅有本地 Database
Ownership、共享 Catalog 可见性或前端隐藏都不能绕过 active relation 校验。调用者对共享 Catalog 有
`workspace.show_catalogs` 时，即使没有可读 Database 也返回空目录；没有 Catalog 权限且没有可读后代时不返回该节点。按 ID
读取 Catalog 详情仍需点查 `workspace.show_catalogs`，无权对象按存在性隐藏返回 `404`；其 Database 列表使用
`catalog.show_databases` 集合 filter，没有可见 Database 时返回 `200` 空列表，Catalog 本身不存在时才返回 `404`。共享节点统一标记 `read_only`，
Table 内容继续执行 MatrixOne DCL 运行期边界。

同一保护适用于普通 Database info/children/ref、Table metadata 和按 ID 入口：命中未清理的 subscription
Database 时必须由 Core Catalog API 验证 `catalog.show_databases`/`table.query` 和 active relation，并返回只读的逻辑
Catalog 投影，inactive 残留返回 `404`。Backend 不直接读取 Data Share 产品身份表；`DataShareReadService` 只负责
publication/subscription 读模型，表的物理字段、DDL 和统计信息由目标 workspace 当前 Verified Effective Role 的
MatrixOne 连接读取。只过滤列表或依赖前端隐藏不能阻止已知 `database_id/table_id` 的直接请求。

workspace 删除不检查 MatrixOne publication 是否存在，也不以 publication 的 `MutationSagaID` 阻塞删除；
owner 和 Sandbox 删除条件保持不变。删除 source workspace 会撤销其对外共享。target subscription、Data Share mode、
迁移状态、Saga 和 projection 不阻止 workspace 删除。删除事务在 workspace 仍可访问时按 mode 快照
Legacy tenant subscription 或 global target projection，随后继续物理删除 workspace metadata 并写入既有
account deletion recovery；提交后只执行一次异步 best-effort target cleanup，从 source publication 的显式
account 列表移除已删除账号，并精确删除 Legacy source target row 或 global target subscription projection。
删除 target workspace 时，source publication、其他 target 和通配发布保持不变。global 清理删除以该 workspace
为 source 或 target 的全局发布订阅记录，source workspace 自身的 MO publication 随账号删除。该 cleanup 不创建 durable Saga、tombstone、
startup/timer retry 或人工恢复状态；失败只写包含稳定 workspace/publication/subscription identity、storage
mode、阶段和完整 error chain 的结构化日志。现有 Legacy 发布/订阅模块和线上读写语义保持不变。

Catalog 后台发现无法读取的订阅库时，由 Data Share owner 根据成功读取的 MatrixOne `status=2`
确认来源已删除，复用 Database 删除 Saga 自动解绑并清理该库的目录、Ownership 和残留全局绑定。
该系统恢复不授予用户删除权限，不适用于 active、仅被撤权或事实无法读取的订阅。单库扫描或清理失败
记录完整诊断并保留重试，不阻断其他库扫描或服务停止；全局依赖故障仍返回错误。

共享 Volume/File 不属于当前 Data Share IAM 合同。二期实施前必须先在本节定义可信 source resolver、
`catalog.show_databases` 与 source containment 的组合边界、专用 route、撤销语义和运行期重验，再同步 Registry、PEP 和
测试。当前不得把 `data_publish.*`、`data_subscription.read`、target Database Ownership 或 source
`volume.read` grant 推断为跨 workspace Volume/File allow。

历史迁移以 MatrixOne 为关系事实并使用 MatrixOne fact 派生的稳定 ID；旧租户 ID 仅关联辅助元数据。
Catalog 对象暂时无法解析时保留
`catalog_unresolved` 投影；Data Publish、active Data Subscription 或已解析的订阅 Database 完全缺少
canonical Ownership 时，默认 Owner 是 workspace protected `superadmin`，由 cutover 单次幂等写入缺失 Ownership。
已有任何 exact-key Ownership 都不覆盖。缺失记录、异常记录、写入失败或
workspace owner facts 不可用只记录 Ownership 补录结果与完整错误上下文，不得把它们分类为业务 `record_skipped`，也不得单独使已由 MatrixOne 关系事实和稳定
MOI 产品身份证明的对象保持 `global_paused` 或不可访问；后续修复只补权限元数据，不改变业务关系状态。
无法建立稳定 MOI 产品身份的 live MatrixOne fact 不写入全局投影，不进入 MOI Data Share、Catalog
共享目录或 Ownership 补录；其原生 MatrixOne 发布订阅关系继续独立存在，MOI 不修改或删除它。Offset 134
自动 cutover 不因该未纳入 MOI 管理的事实阻塞其他 eligible 对象进入 `global`；后续只有在 exact proof 完整时，system-only
drift/reconcile 才将其重新分类为 eligible。
迁移、drift 和 reconcile 接口仅接受原始 Core system API key，是受审计的系统运维边界，不参与 workspace IAM
allow/deny，也不是 system principal 的业务绕过入口。

## 9. 当前例外与未注册能力

以下能力不应被错误映射到名字相近的 action。它们为什么暂不使用标准对象权限、当前如何保护以及何时退出例外，见[业务权限模型例外登记](10-business-permission-model-exceptions.md)。

| 能力                                              | 当前分类                                | 当前权限边界                                                                                                                 |
| ------------------------------------------------- | --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| WorkItem Catalog list/detail                      | membership-only                         | Backend Verified Effective Role + Core verified-role guard；只返回节点能力元数据                                             |
| Workflow Template                                 | membership-only                         | 当前 workspace 模板投影；内置模板只读，自定义模板按 workspace 隔离，后续创建/运行 Workflow 独立授权                          |
| Workflow Lineage 未完成父资源解析的 read/revision | membership-only transition              | 只允许当前 workspace；能解析父 Workflow 的 rerun 已使用 `workflow.run`                                                       |
| 未挂载 Volume 的文件（含临时候选文件）              | membership-only                         | 文件真实存在且属于当前 workspace，有效成员即可访问；挂载后切换 `volume.read/write`                                           |
| Data Asset 内部 manifest/lineage/state            | transport-only                          | 可信 transport + workspace tenant；不注册 `data_asset.*`，暴露 mounted File/Volume 的 alias 仍执行 `volume.read`             |
| A2A task/manifest/turn/data-part/feedback         | transport-only                          | transport 状态；解析真实 Agent 后执行 `agent.use`                                                                            |
| LLM session/message/tag                           | membership-only transition              | 当前 workspace 会话及按会话派生的 Agent 分组投影；分组只返回有可见会话的 Agent 快照和计数，不能推导 Semantic Model 或 Agent allow |
| Data Share workspace-name projection              | membership-only                         | 最小 `id/name` 投影；查询结果不产生后续权限                                                                                  |
| Connector/Model 临时配置 probe                    | membership-only exception               | 不读取已保存对象或 credential，不产生 read/use allow                                                                         |
| Alerting                                          | membership-only / `blocked-unsupported` | 当前 workspace member 可用；正式产品模型未冻结，不注册虚构 Workflow/Data Task action                                         |
| Apps/HR Screening                                 | membership-only / `poc-not-productized` | 当前 workspace POC；不能成为通用 IAM allow 来源                                                                              |
| 普通 Workflow Dynamic Service                     | object (`workflow.run`)                 | owner 已按发布记录解析可信 Workflow ID，工作区 MCP 和工作流调用入口均执行对应 Workflow 的运行授权                            |
| Skill metadata/version management                 | membership-only transition              | Backend Verified Effective Role + Core verified-role guard；仅操作当前 workspace 的 Skill，不能推导 `agent.*` 或其它对象权限 |
| 对话 Skill 草稿确认 | membership-only transition | `POST /workspaces/:id/agent-runtime-tasks/:task_id/skills/confirm` 只接受 task、call、digest 和是否绑定；服务端验证任务当前用户和 workspace，从 native gateway audit 读取草稿，复用 Skill owner 保存。永久绑定额外进入 `agent.update` 正式代理；包管理 Agent 通过正式 package 发布入口生成新默认版本，系统 Momo 只允许保存。 |
| 对话 Skill 确认状态读取 | membership-only transition | `GET /workspaces/:id/agent-runtime-tasks/:task_id/skills/confirmation` 用相同 task、call、digest 校验读取当前 Skill 是否保存；可编辑 Agent 的当前绑定由 `agent.read` 正式代理读取。只读端点不创建资源，不改写原始草稿或消息事件。 |
| Channel Instance 配置                    | membership-only                         | 当前有效 workspace Role 可管理实例；Web Search 内部执行沿父功能准入；`GET /workspaces/:id/connector-catalog` 由同一 owner 提供连接器目录与已配置状态，复用该 membership-only 边界，不产生独立 resource/action |
| 本工作区 published-mcp 门                         | membership + source object action       | 门面不注册 object action；`tools/list` 复用 Workflow 权限过滤发现，`tools/call` 根据可信发布来源执行 `api_service.run` 或 `workflow.run`，外部 MCP 与内部工具引用不替代来源对象授权 |
| 本工作区 MCP 导入为工具                           | membership-only                         | `POST /workspaces/:id/tools/actions/import-workspace-mcp` 只创建工作区工具，不绑定智能体；走现有 tools 成员代理，不注册 object action。Momo 在用户明确选择已发布服务时可通过独立的 `agent_builder_workspace_mcp` runtime tool 准备工具：以当前 Verified Effective Role 经 `workflow.read` 集合过滤发现服务，经 `custom_operator.read` 集合发现算子，经 `api_service.read` 与 `workflow.read` 核验选定算子及其发布版本，再经现有 tools 成员代理导入；Agent 候选仍执行对应的创建或更新授权。工具的实际调用继续由来源 owner 执行 `api_service.run` 或算子运行授权，runtime grant 不替代这些授权。直接绑定仍走 `POST /agents/:agent_id/actions/import-workspace-mcp` 的 `agent.update` |
| Compute Resource Spec list                        | platform/membership                     | enabled spec 最小投影只要求有效 membership；不产生实例或规格管理权限                                                         |
| Compute Resource Spec mutation                    | platform                                | Core `spec_admin.accounts`；不接受 workspace Role grant                                                                      |
| `/admin/compute-resources`                        | platform                                | `spec_admin.accounts`，不属于 workspace Application IAM                                                                      |

智能体配置读取与新任务加载在既有 `agent.read` / `agent.use` 准入后，由 Agent owner 对本次访问的绑定核对 tool、skill 的存在性。仅当当前资源目录或成功的精确查询确认引用已不存在时忽略该引用；只清理调用工作区拥有的定义或 overlay，写回前重新锁定并读取当前绑定，使用原版本校验和引用索引事务。权限拒绝、查询故障、响应身份不符以及临时禁用不能作为永久删除绑定的依据。清理只减少失效引用，不新增绑定、权限、资源/action，不改写系统目录、归档智能体、已发布包或历史任务；不使用升级 offset 扫描全库。原生工具的存在性来自既有运行时定义，不能因没有持久化 Tool 行而删除绑定；系统 Skill 使用当前 owner 已加载的 bundled 目录，系统定义的更新仍归原启动生命周期。

会话工作区的系统 Skill 正文与发布版本合同在任务准入时冻结；workspace/user Skill 在每次工作区准备时按当前 active catalog 全量刷新，停用或删除后不残留。包归档在实际工作区执行时才经原 `ArchiveSkillFiles` 生成边界读取。读取使用该任务身份、冻结 Role 和对应的发布版本或当前 active 版本，当前 verified-role guard 仍生效；可读清单与包缓存都不是后续读取的 allow，也不扩大任务的工具准入。工作区准备前后继续重验 live task 与 `agent.use`，不新增 resource/action 或鉴权例外。

生成的 MCP App 通过已准入的 `present_mcp_app` 提交当前会话 `work/` 下的相对文件路径。读取复用 SessionWorkspace owner 与任务冻结的执行器，准备前后重验 live task、工具准入和 `agent.use`；托管执行器继续重验 `agent_sandbox.use`。单文件读取只接受普通文件，拒绝目录越界、符号链接及超过声明上限的内容；不创建 Catalog 文件、资源/action 或新的鉴权例外。HTML 内容冻结到同一次工具调用的任务回执，模型结果只含资源标识，页面继续通过原 MCP Apps 资源接口及当前用户准入读取；历史资源不重新读取执行器上的源文件。

绑定系统 MOI 平台 Skill 的 Agent 在新任务准入时，复用 Workflow 的 `workflow.read` 集合过滤发布目录，将当前工作区 ready、enabled 且名称唯一的已发布服务及其输入 schema 纳入冻结工具清单。它们使用 `published__<service_name>` 作为运行时 ID，不写入 Tool 资源或修改 Agent binding；普通 Agent 仍只使用显式绑定的工具。显式 capability policy 继续裁剪这些工具。调用复用 `InvokeDynamicService` 的正式生成边界，以任务冻结 Role 重新裁决可信发布源的 `api_service.run` / `workflow.run` 及运行依赖；目录可见和 task grant 都不构成业务执行 allow。任务开始后新增服务由后续新任务准入，当前任务可经已准入 Bash 的现有 CLI 入口查询和调用。

已发布服务的 MCP Apps 描述随输入 schema 一起进入任务冻结清单，事件和页面资源绑定共用该清单。页面后续的资源读取和按钮调用使用当前请求用户及当前 Verified Effective Role，重新进入 `agent.use` 和来源 owner 的正式边界，不借用任务创建人的身份。资源读取复用 `ResolveDynamicServiceUIResource`，校验冻结 URI 的服务与版本；按钮调用复用运行时工具 owner 和 `InvokeDynamicService`，仅接受清单中 app 可见的工具。该路径不新增资源、action 或授权例外，普通 Workflow 的画布和运行参数仍使用原生交互。

会话浏览器接管先经 `POST /workspaces/{id}/agent-runtime-tasks/{task_id}/browser/token` 完成账号认证、任务归属、冻结清单 Bash 准入与当前 `agent.use` 授权，再签发 60 秒身份票据。`GET .../browser/stream` 仅通过 WebSocket 子协议携带票据，校验 Origin 和路径绑定后恢复原 principal/Role candidate，重新验证当前 direct binding/lifecycle 和 `agent.use`；连接每 30 秒重新授权，最长 10 分钟。票据不是可延续的业务 allow。沙盒只能从任务冻结的执行目标解析：未显式选择执行器时使用 workspace/user/context reservation；显式选择 `sbx-*` 时使用该 managed Sandbox，并在签发、握手及连接重验时经正式 `GetRuntimeBinding` 边界重新验证当前 `agent_sandbox.use`。两种目标不互相降级，不接受客户端指定沙盒、进程或端口。常驻 Sandbox 的 Bash、接管准备与浏览器使用同一 workspace/user/context 私有目录及 profile；查看面板不创建目录或启动浏览器。接管不创建独立资源或 action。画面和限定的键鼠输入复用同一持续连接，显示端 ACK 控制帧背压；接管持有会话独占锁，断线释放。输入和登录凭据不进入模型事件、工具参数或 checkpoint。

Skill 不再提供 `runtime-files` 下载接口或独立读取工具。系统 Skill 使用发布版本；
其他 Skill 在每次 session workspace 准备时按当前 active catalog 全量覆盖。包归档只在准备
过程中经原 `ArchiveSkillFiles` 生成边界读取，Agent 随后直接读取工作区文件。工作区准备
继续重验 live task、manifest、`agent.use` 和冻结 Role；可读文件不授予 SQL、Volume 或其他
资源权限，后续脚本请求分别进入各资源的正式边界。

## 10. 新业务登记模板

新增业务功能时先复制本模板到本文对应业务域；不能只在 Backend 新增 action 字符串。

```markdown
### <Product Resource>

| 字段                 | 值                                                 |
| -------------------- | -------------------------------------------------- |
| resource type        | `<canonical_resource_type>`                        |
| stable object ID     | `<owner service and ID source>`                    |
| workspace/parent     | `<trusted resolver>`                               |
| create parent        | `<workspace or canonical parent object>`           |
| Ownership            | `<write/delete/transfer lifecycle>`                |
| list semantics       | `<read/use filter before count and pagination>`    |
| runtime dependencies | `<resource/action pairs reauthorized at use time>` |

| Action              | 授权层级         | Authorize resource      | Policy scope                 | 业务功能/API 分类 |
| ------------------- | ---------------- | ----------------------- | ---------------------------- | ----------------- |
| `<resource>.create` | workspace/parent | `<workspace or parent>` | 普通对象 `all`；Catalog 数据树按父 scope | ...               |
| `<resource>.read`   | object           | `<resource>/<id>`       | 普通对象 `all`；Database/Volume/Table 可指定对象 | ...               |
| `<resource>.update` | object           | `<resource>/<id>`       | all/specific                 | ...               |
| `<resource>.delete` | object           | `<resource>/<id>`       | all/specific                 | ...               |
| `<resource>.use`    | object           | `<resource>/<id>`       | all/specific                 | ...               |
```

不适用的 action 明确写 `none` 并说明原因。额外的 run/publish/manage/operate/grant action 必须逐项定义授权层级、可信资源、scope、生命周期和依赖资源；不能把不同语义隐含进 `read`、`update` 或 `use`。

### Catalog 创建 action 收敛

- Database 创建只检查父 Catalog 上的 `database.create`；Volume 创建只检查实际父 Database 上的 `volume.create`。
- `catalog.create_child`、`database.create_child` 不再出现在权限 Schema 或运行期 requirement 中。IAM 将旧策略分别解释为 `database.create`、`volume.create`，保持原 Role、Catalog/Database 类型及 `all`/指定对象 scope；角色保存和对象授权写入将策略及索引写回具体 action。同 scope 的新旧重复授权合并，读取不写策略或改变版本。
- Table 创建继续使用父 Database 上的 `database.create_table` 和 MO `CREATE TABLE`；旧 `database.create_child` 不产生建表授权。建库的 MO 账号级 DCL 投影同样识别迁移后的具体 action。
