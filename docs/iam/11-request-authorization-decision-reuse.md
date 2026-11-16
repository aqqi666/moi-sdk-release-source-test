# MOI IAM 请求级授权裁决复用

本文补充说明[请求与运行期合同](03-request-runtime-contracts.md)中的授权裁决生命周期，包括顶层 BFF 请求的数据树授权计划和 Mowl 内部运行时延续。Core 始终是唯一 PDP；两种生命周期不得混用。

本文区分两件容易混淆的事情：独立受保护请求之间不能复用 allow；已经通过入口准入的 Mowl Task 可以在内部调度、WorkItem、retry 和 recovery 中延续同一份 durable 运行期上下文。Mowl 内部延续不是新的外部受保护请求。

同步请求中的角色状态类型、首次准入合并、IAM body/header 一致性和 Core fact bag 复用机制见[请求身份与统一准入](12-request-principal-admission.md)。该实现机制不改变本文规定的授权范围和数据边界；当前落地状态由[实现状态](05-implementation-status.md)单独记录。

## 1. 背景

旧执行方式在一个复合接口内对同一主体、Role 和业务动作重复读取权限事实并调用 Core PDP。一次请求可能在 Backend PEP、Core handler、owner service 和内部步骤中多次完成等价校验，历史接口延迟达到约 3 至 6 秒，已经影响基本可用性。

重复校验没有增加新的授权信息：当 workspace、principal、Verified Effective Role、resource、action 和请求生命周期均未变化时，后续步骤只是在重新证明入口已经证明的事实。继续要求每个内部函数或 Mowl WorkItem 重复执行完整 PDP，会把运行时实现错误地当成新的产品请求边界。

当前设计采用两条同时成立的原则：

> 独立受保护请求各自鉴权；同一 Mowl Task 的内部运行时延续不重复鉴权。

## 2. 三层执行边界

```text
外部请求入口
  -> 必须鉴权
  -> 创建 Mowl Task，冻结 actor / workspace / EffectiveRoleId / 入口准入审计元数据
       |
       v
Mowl 内部运行时
  -> 调度、WorkItem、内部 retry/recovery 不重新鉴权
       |
       v
调用 Catalog 数据树或 MatrixOne 边界
  -> 只传 actor / workspace / EffectiveRoleId
  -> 对方按自己的 resource/action 重新鉴权
  -> 不继承 Mowl 保存的 allow

调用 BFF-owned business-object / internal-state
  -> 已确认可信的 BFF/内部调用直接进入业务逻辑
  -> continuation 如存在只作恢复/审计元数据，不形成 allow
```

这些边界不随部署形态变化。Catalog 与 Mowl 无论同进程还是 RPC 调用，非数据树内部调用都不因跨进程形成新的业务 PEP；只有进入 Catalog 数据树或 MatrixOne 数据访问时才形成新的权限边界。已登记的内部 capability interface 可以按自己的签名 grant 合同校验，但该合同不是产品业务 PDP。

## 3. 核心合同

1. **入口强校验**：只有 Core 基于 canonical facts 产生的 Verified Effective Role 和 allow 决策可以进入复用范围。Backend 身份认证、Role Candidate、历史 binding、`system owner` 或本地缓存不能生成 allow。
2. **执行期固定**：同一顶层请求中，已授权业务动作的等价内部步骤复用入口决策，不重复进入完整 PDP。角色或 lifecycle 在执行期间变化，不追溯中止已经准入的业务操作。
3. **范围不可扩大**：复用只覆盖入口已经授权的 workspace、principal、Verified Effective Role、resource/action 和派生内部步骤。出现新的受控资源、不同 action、不同 workspace 或不同 principal 时必须重新调用 Core。
4. **请求结束即失效**：授权结果不能跨独立请求保存为永久 capability。下一次业务请求必须重新读取当前 Role binding、lifecycle、policy、业务资源事实，以及本次实际选择的 allow 来源所需事实；只有 Owner 来源需要读取 Ownership。Ownership 缺失只让该来源不命中，不能阻断显式 grant 或 system Role。

### 3.1 外部请求入口

每个独立的外部 HTTP、gRPC 或 Product SDK 业务请求必须完成自己的授权：

1. Backend 完成账号认证并解析 workspace、Role Candidate 和可信 resource/action。
2. Core 验证 principal、membership、direct binding、Role 和 lifecycle，产生唯一 Verified Effective Role。
3. Core 对当前 resource/action 产生 allow/deny。
4. 当前请求可以在完全相同的授权范围内复用这次 allow，避免内部函数重复调用 PDP。
5. 请求结束后，该 allow 不能替代 Catalog 数据树或 MatrixOne 的独立数据裁决。

固定身份禁止后续步骤重选 Default Role。Core attempt fact bag 复用本次必要读取，未完成裁决仍执行所需的 policy、Role Graph 和资源一致性 fence；活跃请求计划已确认的角色事实及已完成精确范围按下述生命周期复用。统一准入的首次数据树 filter 与后续 filter 使用同一计划匹配和发布入口。关联 ID 相同不足以复用，普通 BFF allow 不能生成数据树计划。

已确认可信的 BFF 和内部调用进入 Catalog 非数据树时无条件通过，不要求 `bff_complete_pep`，也不重复执行产品 PDP；`bff_complete_pep` 若存在只用于携带真实 canonical facts 做审计。Catalog 数据树是独立授权边界，但不是重复授权边界：Core 为当前顶层 BFF 请求产生的数据树计划可以跨 Catalog 子请求复用。普通 BFF 业务 allow、UI `allowed_actions`、Task 运行期上下文均不能生成该计划。MatrixOne SQL 执行仍遵循数据面合同。

#### 顶层 BFF 请求的数据树计划

Backend 在 workspace 入口创建内存中的请求状态，生成独立的 256-bit 随机请求实例，包围身份解析、业务 PEP 和全部 Catalog 子调用；退出入口时清除计划并关闭状态。实例不取自外部 `X-Request-ID`，后者继续只作诊断。后台脱离 cancellation 的 context 也不能在请求结束后发出计划。禁止把状态写入 Task、持久化、进程级缓存或下一次请求。

后台 DDL 元数据同步、A2A 会话持久化等独立操作由其 owner 新建授权生命周期，只保留调用身份和链路，不继承原 HTTP 请求的数据树计划。A2A owner 负责覆盖消息写入确认、事件和最终消息保存、会话标题恢复，并在同步失败或后台操作结束时关闭独立状态；HTTP 返回或 SSE 断连不能关闭仍在工作的持久化 owner。会话消息和标题属于非数据树内部状态，对可信调用不重复执行业务 PDP；若独立操作访问数据树，必须在新生命周期内进入 Core，不能延长或恢复原 HTTP 请求的 allow。

Core 在入口首次确认 Effective Role 后，将 principal、workspace、唯一 Role、已验证的 canonical Role lifecycle 事实及 system Role 分类绑定到请求。后续 Role resolver、主 Role lifecycle 检查及其 fence 只消费该可信事实，不重新选择默认 Role，也不重复读取绑定或主 Role lifecycle；继承 Role 的事实仍由新 scope 的 PDP 按需读取。普通业务 PDP 的 allow 不写入数据树计划。

请求计划同时原样保存首次选择 Role 的 `Source` 和 `Version`：`explicit_override` 的版本为 0，`default_role` 携带正数 Default Role 版本。workspace creator 入口明确选择 protected superadmin，记录为 `explicit_override`。复用或跨进程恢复不能将来源改写为 transport/cache 标记，也不能重新读取 Default Role；SQL 连接投影和持久化权限变更 intent 继续消费这份选择事实。请求计划本身不得进入持久化 intent；重放是新请求，仍按既有恢复合同重新准入。缺失或非法的来源/版本组合属于无效内部合同。

数据 owner 解析 canonical resource/action；已挂载文件先映射到 Root Volume，按去重后的 Root/action 使用 `IAMBatchResourceActionProjection` 一次补充未覆盖点。一个 Root 的 1、100、1000 个同 action 文件只计算一次。集合门禁复用 `IAMResourceAccessFilterPlan` 的完整查询范围，point 与 collection 保持分离：普通 Role 的 collection `all` 不能直接变成任意新 resource 的 point allow。新 action/resource 必须由 Core 补充；新 principal/workspace/Role 进入独立绑定的 Core 计划，不能命中旧计划。补充和精确命中均由 Core owner 完成，Backend 只传递不透明结果。普通 Role 的 canonical action `all` 在同一 scope 计算内先行判定，命中时不读取目标 metadata/Ownership，只记录本批精确点；不足时才解析候选资源。每次实际批量裁决沿用 Core 审计事件的 reason、稳定事件 ID 与 request/trace 字段，精确复用不重复写审计。

文件、文件夹及卷的 `volume.read/write` 产品 PEP 将本次访问的文件、Volume 或 Data Asset 标识和服务端选择的 `volume.read` / `volume.write` 一次提交给 Core 的 Volume owner。该内部准备接口只接受活跃请求的可信 delegated transport；Core 解析 canonical Root 并批量补充同一请求的数据树计划。BFF 不先逐 Root 调用普通 `Authorize`，也不把业务 allow 转换成数据树 allow。已验证的 Admin/SuperAdmin 在任何目标解析之前完成数据树准入。普通 Role 的单 Root 或所属 Volume 约束由 owner 在准备阶段校验；Admin/SuperAdmin 已有全量范围，不为这些授权目标约束查询元数据。实际对象存在性及业务状态由业务接口负责。

未挂载 Volume 的文件遵循[workspace 成员访问合同](08-business-permission-model-catalog.md#53-volume-与文件)。Core owner 确认文件真实存在、属于当前 workspace 且无挂载关系后，复用本次请求已经验证的成员身份即可准入，普通 Role 不需要额外的 `volume.*` 权限。准备接口只传回请求绑定的 Verified Effective Role，不为未挂载文件写入 `volume.*` 点裁决；文件 owner 使用同一归属解析器确认当前精确文件仍未挂载后复用成员身份。文件产物单查与批量桥接门禁也消费该分类；混合批次只对已挂载部分匹配去重后的 Root/action 计划，不把未挂载状态当作 404。该准入只适用于本次请求中的精确文件及其未挂载状态，不能伪装为某个 Root 或全部 Volume 的授权计划；文件挂载后必须按目标 Root/action 重新进入 Core。目标查询失败、挂载关系异常或无法确认文件归属时 fail closed，不能回退为成员访问。Admin/SuperAdmin 继续使用全量快速路径，不为这一分类增加权限准备查询；实际文件的存在与 workspace 仍由业务 owner 校验。

批量准备失败保留原始错误链、失败阶段、稳定原因及 workspace/principal/Role/resource/action 和 request/trace；批量 PDP 裁决失败同时记录失败审计，不能只留下通用 HTTP 503。内部计划请求不合法与 Core 响应合同损坏是不同终态：前者为 `403 / catalog_authorization_contract_invalid`，后者由 Backend 判定为 `502 / catalog_authorization_response_invalid`。BFF 保留这些分类并本地化提示，不合并成用户参数错误或普通权限拒绝。

Owner 派生的集合范围在 Core 完成 active Ownership 校验并物化为精确资源 ID 后冻结；后续业务 SQL 使用这份 ID 范围，不携带再次查询 Ownership 的权限条件。业务数据本身的存在和生命周期检查仍由 owner 执行。

跨子请求的集合计划只保存完整查询范围、绑定与版本以及必要的来源分类。逐资源的 grant/statement ID、Role 路径和 Ownership 版本等裁决解释不重复进入传输计划；点裁决及其审计仍使用 Core 原始完整来源事实。精简不能丢弃或扩大资源范围，不能把普通 policy all 升级为 system Role，也不能把集合范围用于点授权。分页发生在授权范围计算之后，缩小页大小不能替代传输计划的精简。

Backend/Core 分进程时，现有 system-authenticated delegated transport 增加两个闭合字段：

| 字段 | 生产者与消费者 | 合同 |
| --- | --- | --- |
| `X-MOI-Catalog-Authorization-Request` | 活跃 BFF 请求状态 → Core | 随机请求实例；单独出现不产生 Verified Role 或 allow |
| `X-MOI-Catalog-Authorization-Plan` | Core → BFF 内存 → 后续 Core 子调用 | 版本、实例、principal、workspace、Verified Role、system Role 分类、精确点决策和集合查询计划；由 Core 用现有 system key、专用签名域签发并完整性校验 |

接收方先认证 system transport 和 delegated principal，再验签并匹配所有绑定。重复 header、字段组合不合法、篡改、身份或实例不匹配均拒绝，不降级为重新猜测角色。错误公开分类为 `catalog_authorization / catalog_authorization_contract_invalid`，原始内部原因进入受控日志；计划内容和签名不得写日志。内部 header 大小有明确上限，超限 fail closed，不截断授权范围。

BFF 通过现有 SDK transport decorator 在实际 HTTP 发出时读取最新计划，并在收到响应 header 后接收补充；同一请求的并发子调用在这个阶段串行，响应 body 仍可并发消费，不同顶层请求互不等待。生命周期由活跃 BFF 请求 owner 强制执行，签名不把结果变为公开 bearer capability；runtime continuation 和 system operation 不携带它。未来 Core 合入 Backend 时可以直接传递 Core 的 request context，移除编码和传输层，PDP 与匹配语义保持不变。

已验证的 Admin/SuperAdmin 直接得到全量数据树范围，跳过权限准备、目标 Root/文件元数据、Policy、Role Graph 和 Ownership 查询；业务 owner 仍负责实际对象的存在、workspace 和业务生命周期。首次门禁或范围补充时 Core/PDP 不可用必须 fail closed；已完成且精确覆盖的门禁不再依赖 PDP 的可用性。数据本身的读取和跨进程业务 HTTP 仍须正常完成。

| 事件 | 当前请求 | 后续新请求 |
| --- | --- | --- |
| Role 被解绑或 disabled | 已开始且范围未扩大的操作可以完成 | Core 重新校验并拒绝 |
| Default Role 被修改 | 当前 Verified Effective Role 不切换 | 按新的候选选择规则重新校验 |
| Policy 或 Role graph 被修改 | 当前已授权 action 不重新计算 | 使用最新 canonical facts 裁决 |
| 资源 Ownership/lifecycle 变化 | 不能借旧决策访问新的或已变更资源范围 | 重新解析业务资源与 lifecycle；仅在采用 Owner 来源时读取 Ownership 并重新裁决 |
| Core 在执行中不可用 | 已取得裁决的等价本地步骤不重复调用 Core | 新请求 fail closed |

### 3.2 Mowl durable 运行时

受信任的外层业务 owner/Task 创建入口先完成产品准入，再把 canonical actor、workspace、`EffectiveRoleId` 和入口准入审计元数据冻结进 `mowl_task.runtime_context_json`。Task 的已接受业务状态决定 Mowl 是否继续调度；这些冻结字段只证明创建来源并维持内部运行身份，不形成 durable allow、capability 或新的 IAM scope。WorkItem、节点和内部执行图只是该 Task 的实现细节：

- Mowl 调度、Case/Token 流转和内部 WorkItem invocation 不是新的产品请求；
- 内部自动 retry、进程重启 recovery 和 cron fire 继续使用同一 Task 的 durable context；
- WorkItem 是内部运行时实现，不是 Application IAM resource，也不是 PDP；
- WorkItem 不重新选择 Role，不读取 Default Role，不调用 Core 证明自己可以被调度；
- `BusinessActionAuthorized` 只记录创建入口当时是否执行过产品 action 准入；Mowl 可以恢复该值用于审计，但不解释、升级或以它控制内部 WorkItem 调度。

`BusinessActionAuthorized=true` 只记录 Task 创建入口曾完成业务准入，不产生额外的内部调度 capability。无论该字段为 true 还是 false，Mowl 都按已接受的 Task 业务状态恢复和继续内部执行；该字段不能作为调用另一个受保护服务的授权证明。

本文后续所称“Task 执行合同内步骤”，是指同一 Task 执行合同内、尚未进入 Catalog 数据树或 MatrixOne 数据边界的步骤。是否跨进程、发生网络调用或产生副作用，不单独决定它是否形成 IAM 边界。

### 3.3 数据边界与内部 capability

**唯一已登记的 Task-continuation sender。** `moi:workflow.trigger -> Catalog POST /api/v1/workspaces/:id/tasks` 延续已经通过 BFF -> Core 入口 `workflow.run` 的同一 Task 上下文。专用 `GetForTaskContinuation` 只发送冻结 actor、workspace、Verified Effective Role 和登记的 continuation 元数据，不含 Role Candidate、`IsWorkspaceOwner` 或 `AuthorizedActionFacts`。Catalog Task 是非数据树接口，对已确认可信的 BFF/内部调用无条件信任，不校验 continuation 或重做 `workflow.run`；元数据仅用于恢复/审计，不能形成 owner bypass、durable allow 或下游数据权限。child 后续访问 Catalog、Database、Volume、File、Table 或 MatrixOne 时仍由数据 owner 按当前 canonical facts fail closed。

WorkItem 只有访问 Catalog 数据树或 MatrixOne 数据边界时才形成新的授权边界：

- 传递 canonical actor、workspace 和 durable `EffectiveRoleId`；
- durable `EffectiveRoleId` 是接收方的唯一 Role 输入；重新鉴权读取的是同一个冻结 Role 的当前 membership、direct binding、Role lifecycle 和 policy facts，不是重新选择所谓“当前 Role”或“最新 Role”；
- 冻结 Role 不再有效时，接收方拒绝当前调用，不得选择其它 Role 继续执行；完整的选择不变量以[外部与内部角色选择边界](03-request-runtime-contracts.md#4-外部与内部角色选择边界)为准；
- 数据接收方按自己的 canonical resource/action 调用 Core PDP；
- 不把 `mowl_task.runtime_context_json` 中的 `BusinessActionAuthorized` 转换成下游 skip、allow header 或永久 capability；
- `task_id`、`case_id`、WorkItem 名称和 system transport credential 都不能替代数据树授权。

Catalog 进程中的 Data Asset 内部 manifest/lineage/state 并非独立 IAM resource/action：它接受可信 BFF/普通内部 transport，不要求 `bff_complete_pep`、数据树 contract 或 runtime continuation，只处理匹配 workspace tenant 和必要的内部状态完整性，不能从关联 Volume、File 或 Semantic Model 推导 allow。`data_asset_state_v1` 可以作为登记 Worker sender 的可选 metadata 到达，但接收端不消费它作为门禁或 allow。Data Dashboard 的 `execution-spec`/`evaluate-alert` 对可信 BFF/内部调用无条件进入，不要求完整 `bff_complete_pep`，也不重新调用 `data_dashboard.use` PDP；Worker continuation 如存在只使用登记的 `data_dashboard_refresh_v1` 元数据。两类非数据树路径都不授予逻辑 Catalog 数据树、Dashboard source Table 或 MatrixOne 数据的访问；这些独立数据边界仍分别执行 current-role `volume.*`/`table.*` 或 MatrixOne 数据权限合同。

内部 capability interface 使用另一类合同。Astra Agent 在 A2A 入口通过 `agent.use` 后签发 task-scoped `RuntimeGrant`；Catalog Model Gateway 只验证 grant 的签名、有效期以及冻结的 task/manifest/binding/selected model 范围，不重新执行 Core IAM PEP。`RuntimeGrant` 不是 Mowl durable allow，不能由 `BusinessActionAuthorized` 推导，也不能授权 Volume、Workflow、Connector、MatrixOne 或其它受控资源。权限变化影响下一次 A2A Agent 准入，不追溯中断当前 grant 已覆盖的模型调用。

Catalog 非数据树业务 route 信任已确认的 BFF 和内部调用，不重复解析产品 action；有权限模型的批量读接口可按过渡约定使用 `ResourceAccessFilter`。Catalog 数据树 route 才根据实际操作解析 canonical resource/action，并使用收到的 actor、workspace 和 `EffectiveRoleId` 调用 Core；Model Gateway 等已登记内部 capability interface 仍只验证自己的专用 grant。任何 endpoint 都不能虚构业务 action，也不能把 system credential 或 Mowl metadata 解释成数据树 allow。

Catalog/Core 不应根据普通 `task_id` 回查 Mowl 的加密上下文来生成 allow。`task_id` 不是授权证明，这种回查还会让受保护服务反向依赖 Mowl 存储并增加热路径查询。运行期 transport 可以自动携带 actor/workspace/Role，但业务 WorkItem 不应手工拼装权限规则。

## 4. 具体场景

| 场景                                                                 | 是否重新鉴权                                                               |
| -------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| 用户调用创建/运行任务接口                                            | 是                                                                         |
| Mowl 调度下一个 WorkItem                                             | 否                                                                         |
| Mowl 内部自动 retry                                                  | 否                                                                         |
| Mowl 进程重启后恢复 Task/Case                                        | 否                                                                         |
| 用户创建、更新、启停 cron/schedule                                   | 是                                                                         |
| 已启用 schedule 在 Mowl 内部 fire 既有 Task/automation               | 否                                                                         |
| 用户调用独立的 retry/resume API                                      | 是                                                                         |
| WorkItem 进入 Catalog 数据树或 MatrixOne                               | 由数据 owner 按 canonical resource/action 重新鉴权                         |
| Dashboard 调用 execution-spec/evaluate-alert                         | 否；可信 BFF/内部调用直接通过，Worker continuation 仅作登记的审计/上下文元数据，均不重跑 Dashboard PDP |
| 受信任 route 读写 Data Asset 内部 manifest/lineage/state             | 否；只验证可信 transport、workspace tenant 和内部状态完整性                |
| Astra Agent 调用 Catalog Model Gateway                               | 不重复执行 Core IAM PEP；验证 task-scoped `RuntimeGrant`                   |
| WorkItem 打开 MatrixOne 数据连接                                     | 使用冻结 Role，按 MatrixOne/Core 数据权限合同校验                          |
| BFF/内部调用进入 Catalog 非数据树                                    | 无条件信任，不重复业务 PDP                                                  |

判断标准不是函数名里是否出现 retry、recovery 或 callback，而是它是否形成新的外部受保护请求边界。同一个动作既可能由用户通过独立 API 发起，也可能由 Mowl 在同一 Task 内部自动执行；前者重新鉴权，后者不因调度动作本身重新鉴权。

cron/schedule 的创建、更新、启用和停用属于新的外层业务请求；只有已经准入并启用的 schedule fire，才能按其冻结的 Task/automation 合同作为内部延续执行。

## 5. 一致性语义

| 事件                        | Mowl 内部运行时                                                 | 下一次外部受保护请求                     |
| --------------------------- | --------------------------------------------------------------- | ---------------------------------------- |
| Role 被解绑或 disabled      | 已准入 Task 的执行合同内步骤可以继续                            | 接收方重新验证并拒绝                     |
| Default Role 被修改         | Task 的 `EffectiveRoleId` 不切换                                | 新顶层请求按新的候选选择规则鉴权         |
| Policy 或 Role graph 被修改 | 不追溯停止 Task 执行合同内步骤                                  | 接收方使用最新 canonical facts 裁决      |
| Core 在执行中不可用         | Task 执行合同内步骤未进入受保护服务时不重复调用 Core            | 受保护服务 fail closed 并保留 `503` 分类 |
| Mowl 进程重启               | 从 durable context 恢复同一 actor、workspace、Role 和入口 allow | 恢复后首次外部受保护调用仍重新鉴权       |

这项取舍牺牲的是 Task 内部调度阶段的实时撤权，保留的是每个独立受保护服务请求边界上的实时授权。它不允许跨服务 decision cache，也不允许接收方把持久化布尔值当作自己的 resource/action allow。

## 6. MatrixOne 数据面

Application IAM allow 不授予 MatrixOne 数据权限。WorkItem 打开 SQL/MatrixOne 数据连接时必须使用 durable `EffectiveRoleId` 建立对应 Active Role 连接，并遵守 MatrixOne/Core 数据权限合同：

- 不选择 Default Role，不做 Role union；
- 不使用 system credential 代表最终用户访问数据；
- 不把 Mowl 保存的 `BusinessActionAuthorized` 转换成 DDL/DML allow；
- MatrixOne/Core 对当前 Role 或数据权限的拒绝保持原始错误分类。

## 7. 性能与验证

实现和测试应同时证明性能收益与授权边界：

- 一个外部请求内不因内部调用层级重复执行等价 PDP；
- Mowl 内部 WorkItem、retry、recovery 和 cron fire 不因调度本身调用 PDP；
- Mowl Task 创建时完整冻结 actor、workspace、Effective Role 和入口 allow，恢复后保持一致；
- WorkItem 进入 Catalog 数据树或 MatrixOne 时，只连续传递 actor/workspace/Role，数据接收方使用与 Task durable context 完全一致的 `EffectiveRoleId` 重新鉴权；Catalog 非数据树信任可信 BFF/内部调用，不以该上下文重做业务授权。Default Role 变更不会切换该 Role，冻结 Role 失效时不会 fallback 到其它 Role；
- Data Asset 内部状态回归证明只接受可信 transport、workspace tenant 和完整内部引用，不执行 `volume.*` 或 `semantic_model.update` PDP；实际 mounted File/Volume mapping 的 deny、Role mismatch 与 Core unavailable 仍必须独立 fail closed；
- Dashboard 回归证明可信 BFF/内部调用的 `execution-spec`/`evaluate-alert` 直接通过，Worker 如发送只使用登记的 `data_dashboard_refresh_v1` 元数据，二者都不重跑 `data_dashboard.use`；source `table.read` 与 MatrixOne 数据权限仍独立拒绝；
- Astra Agent Model Gateway 只接受并验证专用 `RuntimeGrant`，不接收 Mowl durable allow，也不执行 `model_backend.use`；
- 外部 retry/resume API 与内部自动 retry 使用不同的鉴权合同；
- Core 403/503、workspace/Role mismatch 和 MatrixOne 数据权限拒绝不被内部运行时改写成 allow；
- 日志和 trace 能区分外部入口授权、Mowl 内部延续和数据边界重新授权。

性能优化应通过减少同一请求或同一 Mowl 内部运行时中的重复鉴权，或使用已登记、签名且严格限域的专用 grant 实现。不能让一个服务继承另一个服务的 allow、让 Catalog/Core 回查普通 `task_id`，或恢复 system owner、本地 policy、Role union 等 fallback。
