# MOI 业务权限模型例外登记

> 最后更新时间：2026-09-01

大多数 MOI 功能都按“业务对象 + action”鉴权。例如读取 Agent 使用 `agent.read`，运行 Agent 使用 `agent.use`，读取已挂载 Volume 的文件使用 `volume.read`。完整目录见[业务功能权限模型目录](08-business-permission-model-catalog.md)。

本文只记录不能直接套用这套模型的功能。下面先说明多项功能共用的权限规则，再说明 A2A、Data Share workspace name、Compute Resource Spec 和 workspace 垃圾回收的特殊边界。

本文不是权限绕过清单。BFF 对真实 Agent、Workflow、Connector 等产品对象完成标准 action 鉴权；可信 BFF 到 Catalog 的非数据树调用及后续已确认内部调用直接通过，不重复该业务 PDP。实际进入 Catalog 数据树或 MatrixOne 的数据边界通常仍按该边界的标准 action 调用 Core；唯一登记的创建例外是知识库初始 provisioning，边界见第 8 节。

## 1. 什么叫“只校验工作区成员”

“只校验工作区成员”不是只要登录就能访问。Backend 和 Core 仍必须确认：

- 请求属于一个真实且有效的 workspace；
- 用户是该 workspace 的有效成员；
- 用户当前选择的 Role 已由 Core 验证且仍然有效。

校验失败返回 `403`，Core 或必要事实不可用返回 `503`。通过校验只代表“可以进入这个工作区功能”，不代表可以读取任意已挂载文件、运行 Agent、查询 Table 或使用其它业务对象。

## 2. 只校验工作区成员的功能

下表中的功能都要求调用者是当前 workspace 的有效成员，并持有 Core 已验证的 Effective Role。除表中明确写出的限制外，它们目前不再检查独立的对象 action。

| 功能 | 通过成员校验后可以做什么 | 为什么暂不使用对象 action |
| --- | --- | --- |
| 首页任务执行状态统计 | 读取当前 workspace 最近 7 天的任务状态聚合 | 首页概览不设独立权限；仍验证成员、Direct Role binding 和 lifecycle，不授予任务详情或操作权限 |
| WorkItem Catalog | 查看节点类型、参数等能力说明 | 它是 Workflow 编辑器使用的系统能力目录，不是用户创建和拥有的业务对象 |
| Workflow Template | 读取内置模板；读取当前 workspace 的自定义模板，写操作继续受现有 owner/admin 限制 | 模板尚未被定义为可独立共享和管理的产品对象 |
| 部分 Workflow Lineage 查询和 revision | 查看当前 workspace 的 Lineage；能够解析到父 Workflow 的 rerun 已使用 `workflow.run` | 其余入口还不能全部可靠解析到父 File、Workflow 或 Execution |
| 未挂载 Volume 的文件（含临时候选文件） | 有效成员可访问当前 workspace 中真实存在、经 Core 确认未挂载任何 Volume 的文件，不要求上传者、Owner 或管理员身份 | 适用于所有未挂载文件；按[Volume 与文件](08-business-permission-model-catalog.md#53-volume-与文件)合同，挂载后改用 `volume.read` 或 `volume.write`；查询失败、跨 workspace 或挂载关系异常不得视为未挂载 |
| LLM session、message、tag | 访问当前 workspace 的会话数据，以及按可见会话派生的 Agent 分组快照和计数；普通 chat 可从本人原 provider 主体已提交的完整轮次创建同 Agent 的独立分支。分支仅复制展示快照与稳定 Catalog 引用，远端前缀仍由 Astra owner 管理。持久 Saga 冻结 principal、候选与 Verified Effective Role，重启经官方 restore_access 边界重新校验 membership/lifecycle；实际续聊仍走普通 agent.use、模型及文件准入，不复制执行权限 | 会话分组不是 Agent 对象枚举，不能据此获得 Agent 或 Semantic Model 权限；后续需确定独立 Ownership/action 或可靠父对象 |
| Connector/Model 临时配置 probe | 测试请求中临时提供的配置，不读取已保存对象或 credential | 它只验证临时配置是否可用，不能产生 Connector 或 Model Backend 的 read/use 权限 |
| Alerting Rule、Receiver、History | 访问当前 workspace 的告警数据和操作 | Alerting 尚未确定稳定 ID、action、敏感配置和运行期执行边界 |
| Apps / HR Screening | 访问当前 workspace 的 POC 数据 | 功能尚未正式产品化，也未确定 Ownership 和依赖资源边界 |
| Runner/Sandbox External Catalog | 列出当前 workspace 的模型 Offering，并签发绑定当前 Verified Effective Role 的短期 RuntimeGrant | Offering 是运行 transport capability，不是用户可配置业务对象；入口仍重验成员、Direct Role binding 与 lifecycle，后续受控资源按各自 action 授权 |
| Data Asset 内部 manifest/derivation/parsed manifest/lineage | 可信 BFF 或内部 transport 可直接读写当前 workspace 的内部状态；只做 workspace 与引用完整性检查 | 它是 Catalog 实现状态，不注册 `data_asset.*` action，也不由关联 Volume/File/Semantic Model 派生 PDP；暴露已挂载 File 的 alias 仍按 `volume.read` |
| import/export/structured-load 的隐藏 System Workflow | 产品 PEP 完成 action allow 后，可信 BFF 调用 Catalog 非数据树 execution/readiness 接口；Catalog 以平台 owner 身份安装内部定义并调度 Task，不重复调用 Core 产品 PDP；建表等不可逆副作用前可单独准备定义但不创建 Task | 隐藏 Workflow 是实现细节，不是用户可管理产品对象；Catalog 不把 transport Role 或 continuation 元数据当作额外业务门禁；Volume、Connector、Table 等实际受保护依赖仍由各自 owner 重新鉴权 |
| Skill metadata/version management | 创建、读取、更新当前 workspace 的 Skill metadata 和历史版本，包括切换当前版本 | Skill 尚未定义 canonical Ownership、resource/action 与可信对象 resolver；该边界不能产生 `agent.*` 或其它对象权限 |
| 对话 Skill 草稿确认 | 仅确认当前用户在当前 workspace 的 native gateway 草稿，保存通过既有 Skill owner；永久绑定另经 `agent.update` 和正式 package 发布边界 | 延续 Skill metadata 成员边界；不新增 Skill object action，不授予 Agent 权限。Skill canonical 模型落地时同步迁入 |
| Channel Instance 配置（Web Search、GitHub、WeCom、Slack、Feishu、QQ Mail、Kubernetes 等） | 创建、读取、更新、测试、删除当前 workspace 的 Channel 实例 | native 配置入口按有效 workspace Role 准入；Web Search 独立权限已整组退役，内部搜索沿父功能准入。配置管理将单独设计权限及命名，不沿用已退役名称，也不预设 `channel.*` 或 `*.manage` |
| 本工作区 published-mcp 门 | 对当前 workspace 的 MCP Streamable HTTP 入口做成员校验 | 门面不是独立产品对象，不注册 object action。`tools/list` 复用 Workflow 的权限过滤发现；`tools/call` 根据可信发布来源执行 `api_service.run` 或 `workflow.run`，不能由导入工具或成员身份替代调用授权 |
| 本工作区 MCP 导入为工具 | 将已发布 MCP tools 导入为当前 workspace 的工具记录，不绑定智能体 | 走现有 tools 成员代理，不注册 object action。关闭条件：绑定仍走 `POST /agents/:agent_id/actions/import-workspace-mcp` 的 `agent.update` |

这些边界只是当前产品范围，不应被复制成新的通用权限模式。

## 3. 运行期外部受保护边界

### 3.1 Mowl Task-backed 后台任务

下列功能创建 Mowl Task，因此遵循[请求级授权裁决复用](11-request-authorization-decision-reuse.md)和 [Mowl 运行期执行上下文](../../moi-core/docs/workflow/RUNTIME_EXECUTION_CONTEXT.md)。本表只登记具体业务依赖缺口，不重复定义 durable allow 或重新鉴权规则。创建时保存的 owner classification 只用于审计，不能在恢复时重建 allow/skip fact。

三层运行期合同以[请求与运行期合同](03-request-runtime-contracts.md)和[请求级授权裁决复用](11-request-authorization-decision-reuse.md)为规范事实源。对普通 Worker sender 与 Catalog 数据树或 MatrixOne receiver，sender 只连续传递 actor、workspace 和冻结 Role，receiver 不继承 admission、workspace-verified 或 owner skip，而是按数据边界的 canonical resource/action 调 Core。Catalog 非数据树不是第二个 PDP：可信 BFF 和内部调用的 Data Asset、Dashboard、Workflow/Runtime 内部状态直接通过，不要求 `bff_complete_pep`；Dashboard Worker 如使用 `data_dashboard_refresh_v1`，它只是登记 sender 的审计/上下文元数据，Catalog 不重复 Dashboard PDP。source Table 和 MatrixOne 仍保留独立数据边界。

唯一不同的已登记 sender 是 `moi:workflow.trigger -> Catalog POST /api/v1/workspaces/:id/tasks`。它不是 membership-only 边界、通用 Mowl durable allow、Catalog grant 或 `RuntimeGrant`：专用 `GetForTaskContinuation` 只在可信 system transport 下发送 `runtime_continuation` / `workflow_trigger_task_v1`，携带已准入 Task 冻结的 canonical actor、workspace、Verified Effective Role 和两个 admission 元数据（`WorkspaceAccessVerified=true`、`BusinessActionAuthorized=true`），且不含 Role Candidate、`IsWorkspaceOwner` 或 `AuthorizedActionFacts`。Catalog Task 是非数据树接口，信任该可信内部调用，不校验 continuation 或再次调用 Core `workflow.run`，只处理 Task/`workflow_version_id` 输入和事务完整性；普通 worker client、裸 `task_id`/`case_id` 和 system credential 本身不能获得额外 allow。当前唯一生产调用点是 `moi:workflow.trigger` 的 `WorkflowTrigger`；其它 WorkItem 不得接入该专用 client。它不授权任何 Catalog 数据资源，后续 Volume、File、Connector、Table、Database、MatrixOne 等依赖仍由各自 owner 重新鉴权或按数据权限合同处理。

| 功能           | 已经完成                                                              | 仍需完成                                                                                                                           |
| -------------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Data Task      | 对象权限、Ownership、durable context 和 DB import 的 frozen Role 连接 | 其它 WorkItem 到 Catalog 数据树、其它受保护 owner 或 MatrixOne 的 actor/workspace/Role transport 与接收方鉴权；Catalog 非数据树调用信任可信 BFF |
| Export Task    | 创建、读取、删除、用户重试等入口权限                                  | 到源文件、Connector 和外部目标受保护服务的 Role transport 与接收方鉴权                                                             |
| Semantic Model | CRUD、use、Ownership 和 durable context                               | re-embedding、reconcile 对父 Semantic Model、source、Compute Resource 和数据依赖的鉴权边界；内部模型路由不注册 `model_backend.use` |

### 3.2 非 Mowl 直接调用

直接 chat、embedding、parser 调用不一定创建 Mowl Task，不能假定存在 `mowl_task.runtime_context_json` 或复用 Mowl durable allow。Astra Agent 请求在 A2A `agent.use` 准入后，由 Model Gateway 验证 task-scoped `RuntimeGrant`；未经过该 Gateway 的独立受保护请求仍按[请求与运行期合同](03-request-runtime-contracts.md)完成自己的授权。

| 功能                              | 已经完成                                                                                                                                                                                                                                                  | 仍需完成                                                                                                                                                                    |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 直接 chat、embedding、parser 调用 | Agent 请求已经过 `agent.use` 和 Model Gateway `RuntimeGrant` 验证；独立 Runner/Sandbox CLI 的 External Catalog 重验当前 workspace 成员、Direct Role binding 与 lifecycle 后签发 grant；Catalog `/parsers/parse` 的 JSON `file_id` 路径已验证冻结 Role，并在文件属于 canonical Volume 时执行 `volume.read` | 其它未经过这些控制面的路径，以及未在 M6 已闭环基线登记的 parser receiver，必须解析真实父业务资源并按其 action 授权，同时重验数据依赖；不能虚构 Model Backend runtime action |

这些工作由 [M6 运行期收口计划](plans/m6-runtime-enforcement.md)继续跟踪。未完成前只能保持已确认的最小能力或 fail closed，不能改用 system owner、service credential、工作区成员身份或持久化 owner classification 扩大访问。

## 4. 运行通信：A2A

A2A task、manifest、turn、data part 和 feedback 是 Core 的运行通信数据，不是产品级资源。

- 权限要求：transport 请求必须携带当前 workspace 的 Verified Effective Role；解析到真实 Agent 后，还必须通过 `agent.use`。
- 允许范围：访问当前 workspace 的运行通信数据，或者在通过 `agent.use` 后调用对应 Agent。
- 权限边界：不注册 `a2a.read` 或 `a2a.use`，A2A 也不能代替 Agent 权限。

## 5. 关系展示：Data Share workspace name

workspace name 只是 Data Share 已有关系的辅助展示，不是独立的 Data Share 对象。

- 权限要求：调用者必须持有当前 workspace 的 Verified Effective Role；查询结果还必须属于已有 publish/subscription 关系。
- 允许范围：读取这些关系中 workspace 的稳定 `id/name`。
- 权限边界：查询名称不会产生 `data_publish.*` 或 `data_subscription.*` 权限，后续操作仍按 publication 或 subscription 的 action 鉴权。

## 6. 平台能力：Compute Resource Spec

Compute Resource Spec 是平台统一维护的规格目录，不属于 workspace Role 可以管理的资源。

- 查看规格：调用者必须是当前 workspace 的有效成员，并持有 Verified Effective Role；只能查看已启用的规格。
- 管理规格：调用账号必须在 Core `spec_admin.accounts` 平台管理员名单中，才能创建、修改、启停或删除规格。
- 权限边界：workspace owner、`superadmin` 或 `admin` 都不能替代平台管理员身份，也不注册 `compute_resource_spec.*`。

## 7. Workspace owner 特例：垃圾回收

workspace 垃圾回收是系统维护操作，不接入 MOI 业务 IAM resource/action：

- 产品入口只在 BFF 检查 Core workspace 解析已经冻结的 `is_workspace_owner=true`、workspace membership 和唯一 Verified Effective Role；不能从请求 header、Role 名称或本地 owner 数据推断。
- 通过后使用普通 `coreclient` 调用，不声明 `bff_complete_pep`、不生成垃圾回收 action fact，也不把 owner 或 admission 作为下游 capability。
- Catalog 将已认证 BFF/内部调用视为已经准入，不执行 `Authorize`、`ResourceAccessFilter` 或 execution contract gate；Catalog 只负责 workspace 存在性、请求参数和回收执行。
- 该规则只适用于垃圾回收接口，不能复制为其它系统操作的通用 owner bypass。

## 8. 知识库初始资源 provisioning

知识库创建需要 workspace `semantic_model.create` 和默认 Catalog 的 `database.create`；仅初始根 Volume 是建库动作附带的系统管理资源：

- BFF 完成 `semantic_model.create` 后，由平台编排 provisioning，并向 Catalog 携带默认 Catalog、workspace 和冻结的 Verified Effective Role。
- Catalog 初始化入口通过生成边界以默认 Catalog 的稳定 ID 调用 Core PDP 校验 `database.create`，同时校验默认 Catalog 绑定和父子引用。缺少该权限返回知识库关联数据库创建权限不足；不把 `semantic_model.create` 投影为 MatrixOne 建库权限。
- 建库准入后，初始 raw/processed 根 Volume 不单独要求 `volume.create`，也不构造本地 allow Decision；显式指定其他 Catalog 时继续走普通建库与 Volume 创建边界。
- 平台负责流程编排、回滚和补偿，但 MatrixOne Database 继续以发起用户的 Verified Effective Role 创建，Database/Volume Ownership 也登记给该 Role。system principal 不是资源 Owner。
- 该 Role 只作为最终资源归属和审计事实，不让 BFF allow 短路后续 Database/Volume/File/Table 的读写 PDP。普通数据树创建、知识库追加来源和修复流程不进入本例外。

该例外只覆盖已准入知识库的初始根 Volume，不能扩展为通用数据树 bypass。

## 9. 必须遵守的底线

- 不能把 `authzpolicy passThrough` 单独当作已经完成权限检查；只有已确认的 BFF 服务身份加上 BFF 自身 PEP 才构成产品准入。
- Mowl 与非 Mowl 路径分别遵循各自的运行期合同；调用独立的受保护服务时，接收方必须按真实业务对象鉴权，Catalog 非数据树接收已确认可信 BFF 时除外；Catalog 数据树不能继承上游 allow。
- 不能为了通过 checker 给 A2A、WorkItem Catalog 或临时传输数据虚构 action。
- 某项功能完成标准权限接入后，应从本文删除，并同步更新实现状态、M6 计划和验证证据。
