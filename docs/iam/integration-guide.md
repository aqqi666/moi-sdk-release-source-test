# MOI IAM 接入指南

本文是日常维护的最短流程。任何权限接入、route/action 修改或权限缺陷修复都必须先读[业务功能权限模型目录](08-business-permission-model-catalog.md)；新增或修改权限链路时还必须执行 `.agents/skills/iam-integration/SKILL.md`。

## 1. 先判断权限边界

判断标准不是接口位于哪个组件或是否属于 Catalog，而是它是否直接承担用户业务动作。新功能的设计、评审和权限接入建议必须先写明接口分类、PEP 位置、所用的授权证明或服务身份，以及原因。

- 用户或 BFF 发起的资源读写、管理操作：在该业务动作入口接入 PEP，按资源合同调用 Core `Authorize` 或 `ResourceAccessFilter`。
- A2A 或任务运行入口：解析真实 Agent 后接入 `agent.use` PEP；准入成功后签发 task-scoped `RuntimeGrant`。
- Model Gateway、MCP/Skill 转发等下游运行时数据面：不重复执行用户业务 PEP，只校验上游签发的受限 `RuntimeGrant`，包括签名、有效期、workspace、task、manifest/binding 和模型、工具或技能范围。不得在纯转发 Gateway 中新增 `agent.use`、`model_backend.use` 等业务 action。转发目标实际访问受控业务资源时，仍由该资源 owner 按运行期合同授权。
- Catalog 文件外部模型 HTTPS URL：签发入口要求 Verified Effective Role，并对系统私有 Catalog hierarchy 中的文件执行 `volume.read`；普通 Volume 文件不走该私有检查。外部模型拉取只验 HMAC、文件绑定和 TTL。不得把该数据面当成用户 download，也不得在 GET 上要求 MOI actor 或 live `volume.read`。
- 系统维护、Worker 回调等不直接承载用户业务动作的内部接口：使用对应的 system principal、service principal 或专用调用合同校验，不能套用无关的用户业务 action。Worker 实际访问受控资源时仍必须遵守运行期 reauthorization 合同。

## 2. 冻结资源合同

先在[业务功能权限模型目录](08-business-permission-model-catalog.md)查找目标业务功能与接口，并确认或定义：

- canonical resource type、resource ID 和 workspace/parent resolver；
- 每个业务功能/API 对应的 action、授权层级、scope、condition 和 grant 语义；
- create 的父容器与 Role graph 继承要求；
- Ownership create/transfer/delete；
- list/search/picker 的 filter 和分页语义；
- 从属对象、依赖资源和 runtime reauthorization；
- lifecycle、错误、审计和恢复。

Catalog 树的创建授权必须按最终层级实现：`workspace.create_catalog` 在 Workspace 上只接受 `all`；`database.create`（已发布别名 `catalog.create_database`）在父 Catalog 上接受指定对象或 `all`；`volume.create`（已发布别名 `database.create_volume`）在父 Database 上接受指定对象或 `all`；Table 创建使用父 Database 上唯一的 MatrixOne `database.create_table`。Database 子项导航使用父 Database 上的 `database.show_tables` / `database.show_volumes`，各自支持 `all` 或指定 Database resources；它们不替代具体 Table 的 `table.query` 或具体 Volume/文件的 `volume.read`。Database 更新/删除分别使用 Database 对象上的 `database.update_database` / `database.delete_database`，Catalog 更新/删除使用 Catalog 对象上的 `catalog.update_catalog` / `catalog.delete_catalog`。`catalog.read` 只控制 Catalog 自身的全局查看，`database.read` 控制指定 Database 或全部 Database 的查看。旧的 `catalog.create_child`、`database.create_child` 不属于当前 Registry，不得作为运行时 requirement；IAM 分别将旧授权按原父 scope 转成 `database.create`、`volume.create`。

文档没有该资源/action，或需求与现有模型冲突时，先向用户列出影响和方案。不能复用名字相近但语义不同的 action。

## 3. 选择请求合同

- 对象 CRUD/use：Backend `iampep.Require` -> Core Authorize -> Core current-authorization guard。
- list/search/picker：首次准入时由 Core 校验 Role Candidate；已准入请求只传固定 Verified Effective Role -> Core `ResourceAccessFilter` -> storage 分页前过滤。禁止从已清空的 candidate 构造后续 filter。
- membership-only：只有例外登记明确允许时，使用 Backend verified-role middleware -> Core verified-role guard。

## 4. 实现 owner 路径

1. 在 Core Registry 登记 resource/action/operation 和可信 resolver。
2. 在 Backend 外部 route 解析 workspace 与可选 Role Candidate。
3. 通过公共 Core client 调用 Core；workspace 校验成功后，在同一 Backend 请求上下文中清空 `RoleCandidateID`、写入 `VerifiedEffectiveRoleID` 并保留错误分类，后续 projection 或裁决复用只能绑定 verified fact。
4. 由业务 owner service 解析 resource/parent，不信任请求中的名称、creator 或路径。
5. 同时写入 MatrixOne 和 MOI Catalog 的创建流程中，物理 MatrixOne DDL、Core `SyncMetadata` 和 Direct Owner 登记必须复用同一请求中经 Core 验证的 `VerifiedEffectiveRoleID`；该 IAM Role 映射为 MatrixOne session 的 Active Role，不能分别选择 MOI Owner Role 和 MatrixOne SQL Role。
6. 业务与 canonical Ownership 必须共同完成。同库使用同一 tenant transaction，任一步骤失败整体回滚；跨库或外部副作用复用原持久化命令或 Saga，冻结已验证身份，全部必需步骤完成后才提交成功终态。
7. 创建使用当前 Verified Effective Role 登记 Ownership，使创建 Role 默认获得对象全部普通 Application IAM 能力。登记失败必须返回错误，跨边界创建保留原操作的未完成状态供恢复；删除同样必须在 Ownership 清理完成后才报告成功，确认缺失可幂等继续，存储失败不能作为缺失处理。恢复沿用原操作和身份，不另建元数据补偿队列，也不能仅写日志后丢失失败。业务 lifecycle 决定未完成操作的可见性；对已经存在的对象，Ownership 缺失不能否定其它合法授权来源。完整合同见[Ownership 登记与清理](04-storage-lifecycle-audit.md#33-ownership-登记与清理)。
8. 异步任务保存 actor/Effective Role，在实际受控访问时重新授权。

公共机制迁移按[请求身份与统一准入](12-request-principal-admission.md)和[迁移计划](plans/request-principal-admission.md)执行：业务 service 只消费绑定的 Verified 身份与精确 decision/plan，角色字段由公共 IAM adapter 构造，首个业务裁决尽量合并身份验证。Core 同一 attempt 复用 canonical facts；活跃 BFF 请求的已验证角色与已完成数据树范围通过 Core 请求计划复用，首次合并 filter 使用公共计划入口。未覆盖范围由 Core 补充裁决，未完成裁决所需 fence、PAP 事务及 MatrixOne 数据面按各自合同验证。新接口必须明确准入类别并加入真实 middleware/transport 回归，不能只复制某个既有 handler 的候选读取方式。

公共机制迁移按[请求身份与统一准入](12-request-principal-admission.md)和[迁移计划](plans/request-principal-admission.md)执行：业务 service 只消费绑定的 Verified 身份与精确 decision/plan，角色字段由公共 IAM adapter 构造，首个业务裁决尽量合并身份验证。Core 同一 attempt 复用 canonical facts；活跃 BFF 请求的已验证角色与已完成数据树范围通过 Core 请求计划复用，首次合并 filter 使用公共计划入口。未覆盖范围由 Core 补充裁决，未完成裁决所需 fence、PAP 事务及 MatrixOne 数据面按各自合同验证。新接口必须明确准入类别并加入真实 middleware/transport 回归，不能只复制某个既有 handler 的候选读取方式。

## 5. 同步调用方

当前分支未发布的 API/proto/SDK 变更直接同步 Backend、Core、Product SDK、Frontend、测试和文档，不保留旧 wrapper。Product SDK 只包装 Backend，不直连 Core，也不自行补 Default Role 或业务必填字段。

## 6. IAM Permission-Effect CI 接入

本节只规定 IAM 权限生效测试的 CI 接入方式，不定义新的 resource、action、授权范围或生产运行时 allow 逻辑。具体业务权限语义仍以[业务功能权限模型目录](08-business-permission-model-catalog.md)和 Core canonical Registry 为准。

新增或修改 action 时，涉及 IAM permission-effect CI 的以下改动必须在同一个 PR 中完成：

1. 在对应业务域 coverage manifest（例如 `moi-backend/api-tester/tests/permission_effect/catalog_action_manifest.py`）中登记 action 与真实 pytest node。manifest 只描述 coverage 维度、required node 和能力门禁，不复制 Registry 的 resource、scope、condition 或其它授权事实。
2. 为 action 增加真实 effect case，证明适用的 deny、exact/all、lifecycle、Ownership 或数据面执行结果；仅有 schema、DTO、mock、collection 或 capability-false 合同测试不算 live 生效证明。
3. 需要 MatrixOne DCL、row/column 或其它可选执行能力时，在 Permission Schema 声明明确 capability，并由 live case 验证能力 ready 且执行结果真实生效。fail-closed 分支不能替代正向 enforcement node；参数化或 capability-false case 不能冒充 required enforcement coverage。
4. 确认 IAM 专项 CI 的 path planner 覆盖 owner 代码和 transport，preflight 能精确收集 manifest 声明的 node，JUnit gate 能校验 PR 生成的报告包含 required node 且其 reported outcome 为 passed；该 gate 不独立证明测试 body 已执行，也不提供 execution attestation。失败日志和 collection 清单作为短期 artifact 保留。不要新建平行 workflow，也不要复制 PR diff 或路径判断逻辑；路径选择统一维护在 `.github/scripts/pr_ci_path_plan.py`。

## 7. 验证

按[验证与漂移控制](06-verification-drift-control.md)运行目标资源测试、IAM Core/Shared engine、Backend/Core 合同 checker，以及需要的 MatrixOne/upgrade gate。完成后更新实现状态的代码基线；Registry schema、resource 或 action 变化时同步[Registry 快照](09-business-permission-model-registry.md)并通过 checker。新增临时 membership-only/transport-only 边界时同步[例外登记](10-business-permission-model-exceptions.md)和关闭条件。

修改 Role Candidate、workspace membership、Current Principal projection 或请求级裁决复用时，测试必须经过生产 route 的真实 middleware 顺序，证明 Core 调用前 candidate 存在、验证后 candidate 已清空且 `VerifiedEffectiveRoleID` 已写入；projection 返回的 Effective Role 必须与该请求上下文字段比较，不得再读取已清空的 candidate。不得用直接调用 verifier 或手工拼接 context 替代该回归；SDK/CLI Role transport 变化还必须覆盖真实 PAT 到 `/newmoi/user/info` bootstrap 的端到端验证。

同步 workspace 路由通过 `WorkspaceAdmission` 显式注册，与认证后 `ResolveWorkspaceAdmission` / `RequireResolved` 共同使用。普通对象用 `RegisterAction`，Backend 集合用 `Register(CollectionRouteBinding)`；owner list、最小父资源解析、PAP、数据访问和身份投影分别使用 [12 §4.2](12-request-principal-admission.md#42-将身份验证并入首个业务裁决) 的既有类别。登记失败或遗漏不降为 membership；新增路由必须同时通过实际路由覆盖和 SDK 源码对账。
