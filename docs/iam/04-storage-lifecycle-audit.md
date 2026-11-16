# MOI IAM 存储、生命周期与审计

本文定义 canonical IAM 事实的存储归属、并发控制、生命周期、跨边界一致性和审计要求。具体表名以当前 schema/upgrade 为准，不把表结构清单复制为第二份 schema。

## 1. 存储归属

### 1.1 System storage

System storage 保存跨 workspace 或创建 workspace 前必须存在的事实，包括 canonical 用户、workspace、membership、invitation、账号身份映射、数据库用户投影和 workspace owner credential。

邀请链路中，邮箱、已验证手机号和 GitHub login 都必须先解析到 UC 已存在且可用的账号；查不到时返回 `USER_NOT_FOUND`，不保存邀请或创建占位用户。Backend 只把已解析的 canonical `moi_user_id` 交给 Core。Core 闭环维护 invitation、membership、user profile、Role projection、MatrixOne user 和审计；invitation 表仍不得写入 login / uc_sub / 邮箱 / 手机。面向外部用户的链接邀请是独立渠道，不属于这些定向邀请入口。

### 1.2 Tenant IAM storage

Tenant storage 保存 workspace 内 canonical IAM 事实：

- Role 与 lifecycle；
- direct Role binding 与 Default Role；
- Role graph；
- Application Policy 和编译/发布版本；
- resource Ownership 和 specific grant；
- subject attribute 定义与成员属性值；
- durable lifecycle operation；
- IAM audit event 和 decision facts。

业务 owner 表仍归各业务服务。`created_by`、显示名、legacy tag 或业务状态不能替代 canonical IAM 行。

### 1.3 MatrixOne

MatrixOne 保存 `mo_user`、`mo_role`、grant 和 Active Role 等数据面事实。Core adapter 负责应用 DCL、幂等重试和 readback，但 Application IAM 决策不从 MatrixOne Role 反推。

### 1.4 工作区成员展示事实批量读取

成员列表由 `IAMWorkspaceMemberService` 先执行 `workspace_member.read` 授权，再从 System storage 枚举当前 workspace 的 canonical membership。每条记录必须包含匹配的 workspace、membership ID、canonical user ID 和正 lifecycle version；disabled member 保留其状态。删除请求先持久化同一操作意图，但在 System 删除事务提交前不改变 membership 的 `active`/`disabled` 状态；因此数据库账号清理失败时成员仍按原状态保留。MatrixOne 账号删除成功后，先清理 tenant Role binding、Default Role 和 profile，最后由 System transaction 将 membership 收尾为 `deleted` 并删除账号映射；删除开始的审计在 MO 清理前写入。系统收尾成功但 tenant 清理失败时，成员已不能通过 System membership 进入工作区，未完成的 tenant 清理作为孤儿数据留在操作回执中等待显式修复。删除操作仍可在 active/disabled 成员上通过操作回执显示为删除未完成；系统成员已收尾且仅 tenant 孤儿数据待处理的 `deleted` 记录不再显示，移除成员接口返回成功。内部清理回执与失败 Saga 继续保留，不能改写成清理成功。普通成员详情、当前用户 bootstrap 和授权准入均排除 `deleted` 状态。只有有效成员枚举产生的用户 ID 才能交给当前 tenant 的批量 reader，不能把调用方任意提交的 ID 集合当成成员证明。

删除未完成记录从 System storage 批量读取当前操作的清理状态、阶段、请求/链路标识和更新时间，不依赖可能已删除的 tenant profile、Role binding 或 Default Role。公开原因由业务 owner 按持久化阶段本地化，原始数据库错误只保留在受控存储和日志中；历史回执缺少阶段时明确返回通用的未完成原因，不猜测具体故障。列表读取不执行清理、重试或回执状态修正；成员移除成功以 MO 账号已删除且 System 成员已收尾为准，完整清理成功仍只由原清理收尾写入。有权操作者通过原删除接口显式继续同一删除请求；继续前重新校验当前权限、原 membership、账号及版本，并从 Saga 的第一个未完成步骤继续，不重建已清理的用户或授权。只有精确目标确认不存在才视为幂等完成，数据库连接、读取或写入失败继续返回失败并保留记录。

显式继续删除按当前请求的 principal 与 Verified Effective Role 重新准入，允许另一位有删除权限的管理员或原操作者的另一个有权限 Role 接手。原操作的目标、版本、数据库身份、payload hash 和审计主体保持冻结，不用接手者覆盖；结构化日志关联原主体与本次接手者。启停操作的重放仍要求原主体与原 Role。进程重启恢复继续使用原操作的冻结身份重新鉴权，不自动替换为接手者。

完整成员展示调用 `ListIAMWorkspaceMemberFacts`，按同一组用户 ID 分别批量读取：

1. direct Role bindings 与 Role metadata；
2. Default Role fact；
3. binding aggregate version；
4. subject attribute values；
5. member profile 的 alias 和 description。

非空集合的这部分 tenant 查询从逐成员约 `5N` 次降为固定 5 次；只展示成员姓名的 `ListMemberDisplays` 使用 `ListIAMWorkspaceMemberProfiles`，只执行 1 次 profile 查询；空成员集合不执行这些 tenant 查询。这个计数不包含前置授权、System membership 枚举、系统显示名映射或 Backend 账号资料补充，也不表示完整接口只访问 5 次数据库。

查询使用参数化 `IN`，按 user ID 组装事实后，仍按原 membership 顺序返回。角色列表保留非 deleted Role 的 lifecycle，按 binding 创建时间和 Role ID 排序；标签按 tag ID 排序。缺少可选 tenant 行时保留既有展示语义：角色与标签为 `[]`，缺少 binding aggregate 时版本为 `0`，缺少 profile 时不补造别名，缺少 Default Role 时不推断其它角色；显式 cleared Default Role 仍保留其版本。单条与批量 reader 共用行扫描和 Default Role fact 校验。

任一查询、扫描、迭代或 Default Role 结构校验失败，完整列表整体返回错误，不返回半份成员结果。上述缺失值和 disabled 状态只供展示，不是角色可用性或 allow 证明。批量读取没有新增跨请求缓存，也没有把多条 SQL 提升为同一原子快照；后续授权和 mutation 仍使用各自的 lifecycle、版本校验与 CAS。

实现入口：[成员 service](../../moi-core/catalog/pkg/iamcore/workspace_members.go)、[tenant 批量 reader](../../moi-core/catalog/pkg/service/storage/tenant/iam_workspace_member_reads.go)。

### 1.5 对象权限来源角色读取

Object Permission View 是管理事实视图，不是运行期授权结果。服务在一个 tenant 单语句快照中读取 Ownership、owner Role、Application Policy Grant Index、来源 Role、Policy 文档及 Role Graph，并校验 Index 与文档的内容及 policy version 一致。

- owner 与授权来源 Role 的 lifecycle 可以为 `active` 或 `disabled`；provisioning 必须为 `ready`，生命周期及 provisioning 版本均为正数，Role kind 与 system 标志一致。
- 返回的 owner、direct specific grants 和 all-scope grants 均携带 `role_lifecycle_state`。停用来源的记录完整保留，不能丢弃后返回部分视图，也不能把其存在解释为仍可访问对象。
- 来源 Role ID 集合、Policy 文档集合必须完整匹配，workspace、记录身份与图版本必须有效。角色缺失、额外结果、key 不符、deleted/未知 lifecycle、非 ready provisioning、无效版本、文档/Index 不一致或依赖失败均使本次 view 整体失败。
- 同一快照只读取一次完整的受管理 Role Graph，沿用 Role Graph owner 的边界与预算；没有来源角色时不读图。查询次数不随来源 Role 数量增加，不建立跨请求 Role/graph 缓存。

该展示规则不扩大 inherited/system/MatrixOne 等 included capabilities。公开接口仍要求调用者通过 `role.read` 授权；实际访问仍须通过唯一 PDP 验证当前 Effective Role 与授权来源的 lifecycle。对象授权 validate/apply 的目标 Role 仍须 `active`、`ready` 并满足版本/CAS，不接受管理视图作为授权证明。

实现入口：[Object Permission Service](../../moi/pkg/service/iam/object_permission.go)、[tenant 单快照 reader](../../moi/pkg/dao/tenant/iam_object_permission.go)。

## 2. 版本与 CAS

Application Policy mutation 的 `role_graph_version` 记录 Core 本次 delegation proof 实际使用的图版本。已验证管理员的 delegation fastpath 和空 diff 不读取继承图，此审计字段为空；不得仅为填充该字段额外扫描整张图。普通角色只在同一次 pre-save proof、同一 caller-owned tenant transaction 内共享已读取的 canonical 图和各资源类型的 grant facts，每个 action 仍由同一个 Core guard 独立判断。图读取失败仍使 proof 失败，不得用空字段替代失败；此规则不改变 Object Permission View 或其他依赖图版本的 CAS 合同；角色继承修改不使用全图版本 CAS。 删除已不存在资源的精确 grants 是既有 policy 的收缩，不遍历继承图或新增授权，清理路径同样不为审计单独读取 Role graph，`role_graph_version` 为空；仍保留受影响 Role lifecycle 和 policy version CAS。

会被并发修改的 IAM 事实必须携带独立版本，并通过 compare-and-swap 更新：

- Role lifecycle version；
- binding/default-role version；
- policy version；
- Role graph version；
- Ownership version；
- data privilege version；
- lifecycle operation 的 request ID、payload hash 和状态。

调用方必须发送服务端返回的版本。版本冲突返回稳定 `409`，不能用 last-write-wins、重读后静默覆盖或数组第一项推断 Default Role。

Application Policy apply 在一个 tenant transaction 内完成 policy document、Grant Index、audit/durable operation 和 workspace policy generation 更新。PDP 以 generation before/after fence 证明读取期间没有 policy 变更；generation 缺失、非法或连续变化时 fail closed。Grant Index 是 policy 的派生查询结构，不是独立可写授权事实。

策略替换的移除项来自该事务中锁定的当前 Policy；对象授权撤销只移除该 Role 策略中匹配的项。两者均不依赖目标业务对象是否仍存在，不重新解析被移除项的资源层级。新增项仍严格解析 canonical 资源；全部变更验证成功后统一保存，失败保留原 Policy 和 Grant Index。撤权不免除操作者准入、目标 Role lifecycle、版本 CAS、幂等与审计。

## 3. 生命周期

### 3.1 参与裁决的状态

只有当前 active/ready 的 workspace、user、membership、Role、direct binding 和 Default Role 可以参与 allow；业务对象还必须由 owner service 证明 canonical lifecycle 可参与裁决。Ownership 只是一项正向授权来源，不是业务对象 lifecycle 或 readiness：业务对象仍当前有效、但 exact-key Ownership 缺失、non-active、畸形或字段不完整时，不增加 Owner allow，也不产生 deny 或依赖错误。它对不同 actor/path 的语义如下：

- 普通 Role 的显式 `all`、specific、parent 和 path scope：由 Application Policy 与 owner service 的 canonical 资源/层级事实证明，不要求目标 Ownership。Owner 派生 scope 只接受 exact-key、active 且完整的持久化 Ownership；其它状态只是 Owner 来源不匹配，最终没有其它 allow 时按普通未授权处理。collection 在 owner query 中下推显式 scope；Owner 派生 ID 另行绑定 active Ownership proof。owner service 业务查询始终负责 workspace、逻辑删除和业务 lifecycle。
- 当前已验证 `admin`/`superadmin` 的 Application IAM 业务 point/list/tree/picker：权限裁决不预查目标 metadata 或 Ownership；随后执行的 owner service 业务查询决定对象是否存在和 lifecycle 是否可见，system plan 不携带 invalid-ID 排除或 Ownership filter。
- 直接读取、repair、transfer 或 CAS 更新 Ownership 记录本身的接口只接受健康 active Ownership；记录缺失或异常时返回该权限记录自身的状态错误，不能把错误传播成对象或 workspace 的业务 gate。Object Grant 中，Direct Owner 或通过 active 普通 Role graph 继承到的 Owner，拥有同一 exact 对象全部可授权 Application IAM 操作及对应 grant/revoke 能力；继承边 WGO 不削减 Owner 能力。非 Owner 的 Object Grant 和 MatrixOne Data Privilege 委派由同一 Verified Effective Role 的 workspace `role.update` 管理，这条管理路径不要求目标 Ownership；没有该权限时，当前 exact Owner 才能按 WGO 语义委派自己的对象。目标 action、scope、WGO 和 MatrixOne DCL 仍由 Core/适配器校验。业务资源证明、policy/system Role 等本次实际采用的必要事实不可用，以及预算溢出或未知状态时整体 fail closed；单纯没有 Ownership 不是此类故障。

Role graph 只遍历 active Role；任何边或节点状态读取失败都不能保留旧可达路径。

Role graph 每次裁决从一次 MatrixOne storage query 得到受管理命名空间的完整 role-grant edge snapshot，再执行 cycle、节点和生命周期校验。不对深度、节点数或 workspace edge 数量另设 MOI 上限，也不截断成部分 graph 后继续裁决。

### 3.2 系统 Role

`superadmin` 和 `admin` 是不可变系统 Role。Role mutation、lifecycle、policy 和 inheritance API 都必须在 Core owner 层拒绝对它们的非法操作，不能只依赖 Backend 或 UI 隐藏入口。

`superadmin` 的 binding/default 写入必须验证目标是 workspace owner；`admin` 可对普通成员绑定和设为默认，但不能改变系统 Role 本身。

### 3.3 Ownership 登记与清理

本节只描述权限记录的登记与清理，不为 Ownership 定义业务 lifecycle。

正常创建：

1. 创建成功必须同时完成 canonical 业务事实、以创建时 Verified Effective Role 登记的 active Ownership，以及该操作必需的审计。
2. 同一 tenant database 内，这些写入共用一个 owner transaction；任何一步失败均返回错误并回滚，不能先提交业务对象再把 Ownership 失败变成日志。
3. 跨 system/tenant database、workspace 或外部副作用时，首次写入前持久化完整业务 intent、稳定资源 ID、幂等键与冻结身份，复用原业务 operation/Saga。Ownership 写入和业务激活都是该操作的必需步骤；尚未完成时不能写 completed、对外返回成功或丢弃恢复上下文。
4. 尚未结束的操作发生故障时，恢复必须续接同一 intent，验证已有业务/Ownership 事实后只补必要的未完成步骤；不得凭请求默认角色或新建一条无关操作“修复”旧操作。不能为跨库写入伪造单库原子性。

普通 numeric Owner Role 的 Ownership 新写与 Role 删除共享同一 Role 行锁，锁后验证当前 lifecycle 和 direct binding。普通、prepared finalize 与 derived 登记复用这条写入边界，避免删除清理后再写回旧 Role 的 Ownership。成功回执在新写之前只读重放，不要求已删除 Role 重新出现；受信任 workspace-owner 身份继续沿用原合同。 Data Share 撤销先读取 exact-key Ownership 快照，并一次性按升序锁定同一事务内全部待撤销资源涉及的 Policy Role，再收缩授权并通过 owner/status/version CAS 清理 Ownership；子 Table 清理也在 Role 锁之后，避免角色删除与资源撤销形成反向锁序。 Role 删除不销毁其创建的业务资源，也不撤销其他 Role 对这些仍存在资源的授权；当前删除保留已转移给接收角色的 Ownership。后续显式资源撤销或涉及物理权限的删除按可信资源身份清理相关授权，不以 Ownership 是否存在为前提；历史角色删除已清理 Owner provenance 时，使用既有 internal-service `system` 审计身份记录授权清理，不增加运行期放行来源。

删除：

1. 先按业务对象与当前授权验证删除，再由业务 owner 持久化既有 deleting/等价 intent，保留原幂等身份和恢复上下文。
2. 同库的业务事实、Ownership 和审计收尾共用同一 transaction。普通对象删除允许保留原 Policy 中的精确授权引用及其索引，不同步遍历和改写所有相关 Role；这些引用不再能访问已删除对象，稳定资源 ID 不得复用。Catalog 与 workspace 的删除仍收缩相关授权，并沿用持久 DCL 操作回收建库或查询历史权限；显式 Data Share 撤销继续收缩仍存在资源的授权。exact-key Ownership 确实不存在可以作为已完成的幂等结果；读取失败、畸形事实、CAS 冲突或写入失败必须返回错误，不能冒充“不存在”。
3. 跨库、DCL 或外部删除沿用原持久操作向前恢复；不可回滚的副作用已经执行时，保留未完成操作并继续收敛 Ownership/业务收尾。全部必需步骤完成之前不写成功终态，不把失败只写日志后删除恢复凭据。
4. 已不存在的 canonical 业务对象不能因残留 Ownership/grant 获得 allow。这个授权安全边界不能替代删除操作本身的一致性和完成证明。

Data Share 的创建发布、修改、删除、接受和取消统一遵守[发布订阅生命周期合同](../data-share/moi-data-share-global-cutover.md#08-生命周期)。
上文的“原操作恢复”不要求复活已终结的 Failed：该业务终态和本任务锁释放原子提交，未完成的业务/Ownership
事实继续保留。新的合法用户意图重新鉴权、创建新 Saga、取得同一资源锁，并经各 owner 核验旧回执与 MO 当前事实，
按本次意图补齐或清理；不修改旧失败结果，也不把新删除变成旧创建的补执行。这不降低正常创建共同完成、
同库事务、当前授权或原始凭据校验要求；其他资源的接续方式仍按各自业务合同，不把 Data Share 规则扩散为通用接管能力。

Owner Role 从 A 转给 B 时，Core 只接受对象的当前 Owner（沿用 Direct Owner / inherited Owner 规则）或具有 workspace `role.update` 的 Verified Effective Role，不使用独立 transfer action。转移仍必须验证同一 workspace 的可信目标 Role、active/ready lifecycle 和预期 Ownership 版本，通过 CAS 和审计完成；失败不得改变原 Owner。repair 保留 `resource.ownership.repair` 及其受保护边界。两者都不能直接改业务表 owner 字段。

历史对象 Ownership cutover 推荐优先采用以下受控补录基线：

1. 仅处理 IAM Ownership cutover 前已存在、已进入 canonical 产品资源模型，且 owner service 能精确证明 workspace、资源类型、稳定资源 ID 和当前业务 lifecycle 的对象。
2. “缺失”只表示该 `(workspace, resource type, stable resource ID)` exact key 的 canonical Ownership（当前 schema 中为 `iam_resource_ownership`）完全不存在。已有任何 exact-key Ownership 都不属于历史默认 owner 补录范围，不能被补录覆盖或修复；其当前状态只按正常 Ownership 规则决定是否能派生 Owner 权限，不得形成对象或 workspace 级额外 gate。
3. exact-key Ownership 缺失时没有 Owner 权限来源；显式 all/specific/parent/path grant 与已验证 system Role 的业务访问继续只依赖各自 canonical 授权事实和 owner service 证明的资源 lifecycle。历史补录只是在缺失时登记默认 `superadmin` Owner，不改变其它授权分支。
4. 受控 system migration、显式 SuperAdmin adoption 或受保护 lifecycle mutation 可以异步补录该 Ownership，但普通 read/list/runtime 请求不触发 lazy repair；补录不是显式 grant 或 system Role 业务读取的前置条件，也不能放宽 Owner 派生分支的 active Ownership 要求。
5. 补录若被触发，只通过 canonical Ownership writer 对缺失 exact key 单次幂等写入默认 `superadmin` Ownership。写入失败记录稳定 operation/request/trace ID、对象上下文和完整错误链；不要求为补录维护独立 lifecycle operation、状态机或成功后的持续扫描。
6. 补录无法精确证明 workspace、稳定 ID 或业务 lifecycle 时只终止当前补录范围并记录失败，不写 Ownership，也不改变业务授权结果。target Ownership 缺失、non-active、畸形或冲突只意味着 Owner 分支没有有效事实，不否定显式 all/specific/parent/path grant 或已验证 system Role 对当前业务对象的访问。该基线不适用于尚未进入 canonical 对象模型的 membership-only/transport-only 数据。
7. Root Volume 与 Catalog 启动补录是 best-effort 的单次历史数据修复：每个 workspace 每次启动只查询 exact-key Ownership 完全不存在的 candidate 并执行一轮，已有 active、non-active、tombstone 或畸形记录一律不覆盖。candidate inventory、workspace facts、tenant transaction、writer/readback 或 rollback 失败时，记录 `component`、`operation`、`resource_type`、可用的 `workspace_id`、`failure_scope`、`failure_kind`、`retry_policy`、处理进度和原始错误，继续后续 workspace 与 Catalog 启动；本进程不重试，下一次启动通过同一幂等路径再次查询仍缺失的记录。该补录不安装授权 gate、不改变 readiness，也不把失败转换为 HTTP 拒绝。其它 system migration 是否阻止启动仍按各自业务合同决定，不能套用本例外。

Data Share 历史 cutover 也遵循同一边界：live MatrixOne fact 与稳定 MOI 产品身份决定对象能否迁移；exact-key Ownership 完全缺失时默认补为 protected `superadmin`。Ownership 补录失败或已有异常记录只记录并留给后续修复，不能单独使对象保持 `global_paused` 或不可访问。初始 schema upgrade 不执行该 IAM 写入。

Ownership Impact 提供 owner provenance 的总数、类型统计和有限样本，不作为完整转移清单。角色删除另以 `delete-impact?include_ownership=true` 返回完整集合版本和分页对象清单；角色仍拥有对象时，最终本地事务必须先转移 Ownership，再硬删除本地角色。直接删除缺少转移方案时返回稳定冲突。对象存在、可见及普通业务访问仍按各业务 owner 的生命周期与 Core PDP 判断，不能把角色删除的转移要求扩散成对象访问门禁。禁用角色保留其 Ownership，由当前 Role lifecycle 阻止其提供 allow。

## 4. 原子事务与 Saga

### 4.1 事务与持久恢复边界

本节是 IAM 写接口的设计标准，适用于新增功能和既有功能收敛。先确认真实提交边界，再选择一致性方案；接口和前端交互遵循[公开合同 §1.1](07-public-api-frontend-sdk-contracts.md#11-保存与重试的统一原则)。标准不表示所有既有入口均已完成改造，接入范围与缺口见[实现状态](05-implementation-status.md)。

#### 事务选择

| 真实边界 | 处理原则 |
| --- | --- |
| 所有必需写入可由同一个数据库事务提交、回滚 | 由业务 Service 使用一个本地事务完成，不引入 Saga、恢复扫描或补偿状态机 |
| 跨独立提交的数据库事务，或包含不能随本地事务回滚的 DCL／外部副作用 | 由该业务唯一 owner 复用现有持久化 operation/Saga，明确执行顺序、完成证据和失败处理 |

旧 Backend/Catalog/Mowl 的进程或 RPC 划分不再构成引入 Saga 的理由。迁移后能共享事务的步骤应合并，并删除只为旧边界存在的 intent、补偿、claim 和扫描。反过来，同一进程、同一个 MatrixOne 实例或同一个 tenant provider，也不证明两次独立提交可以共同回滚；MatrixOne DCL 与 MOI 元数据的实际边界须由目标版本的执行方式和事务验证证明，不能用外层 `BEGIN` 的存在推断原子性。

#### 同事务写入

业务事实、lifecycle、Ownership、派生索引、版本、必需审计及该操作已有的成功回执，共用业务 Service 的同一个 owner transaction。DAO 使用该 transaction 的执行上下文，不自行拆分提交；任一步失败都返回错误并整体回滚，提交确认后才返回成功。

普通设置保存直接执行更新，不为判断“和旧值是否相同”额外读取整份权限。授权、对象身份、唯一约束、必要行锁与版本 CAS 继续保留；它们分别防止越权、错误对象和并发覆盖，不属于可删的相等比较。外部协议要求的最小存在性检查按具体操作保留，例如清除不存在的行列规则。

本地事务提交确认丢失时，也不能把连接错误解释为回滚成功。能够通过既有回执或业务事实确认结果时由 owner 确认；不能确认时返回结果未知，不要求每个普通保存接口因此新增操作账本。

#### 跨事务写入

角色继承修改采用下述 §4.1.1 的结果日志合同，不适用本节的恢复、readback、补执行和 Saga 占用规则。其他 IAM 操作保持原合同。

同一产品操作只由一个业务 owner 编排。在首个业务副作用之前保存完整 intent：workspace、canonical actor、冻结的 Verified Effective Role、稳定目标 ID、业务输入、预期版本、operation ID、payload hash 和诊断标识。子步骤复用原操作，不再维护一套独立的恢复 phase、重试器或扫描入口。step 需要 tenant 写入时，按目标 workspace 使用 transaction，不继承来源 workspace 的 transaction manager。

每个 step 必须支持按已提交事实继续执行。这里的幂等要求是“重复处理不破坏最终结果”，不等于发生异常后重新执行整批旧命令。外部结果通过 readback 确认；没有成功回执、SQL 返回错误或客户端未收到响应，都不能单独证明副作用未发生。

MO 数据权限是数据面的执行事实；其跨事务写入按下表处理：

| 已证明的阶段 | 后端处理 |
| --- | --- |
| 旧 Saga 仅保存意图，原执行已停止且确认业务步骤从未开始 | 不因发现旧意图而自动启动，不单独阻塞角色；下一次用户保存走正常准入 |
| MO 可能已执行、部分执行或结果未知 | 先读回，禁止盲目重放旧 GRANT／REVOKE；仍在执行或终态未确认时保留冲突隔离，整角色编辑与独立数据权限确认停止后均允许新保存，旧操作只保留结果和审计，不再占用 Role |
| MO 已确认完成，MOI 提交尚未确认 | 先核对原请求的本地成功回执；已提交则返回原结果，否则只重试 MOI 收尾 |
| MO 与 MOI 均已完成，仅 Saga 最终状态未保存 | 依据成功回执和必要的外部核验完成 Saga，不重新修改 MO |
| 确定性拒绝或持久重试预算耗尽 | 保留失败结果、阶段和错误，停止自动执行，转由业务 owner 和有权管理员显式处理 |

“从未开始”必须有可信的执行记录证明，不能仅凭缺少 tenant intent、Role ID 或成功回执判断。MOI 收尾在一个本地事务内共同提交权限投影、版本、成功回执、必需审计和原操作处置；任何一步失败都不能报告整次保存成功。

跨事务操作必须明确采用向前收尾还是补偿。已确认的 MO 数据权限变更优先向前收尾 MOI；人工同步也以 MO 最新事实为准。创建等有明确撤销语义的操作按各自合同补偿，必须能证明完整恢复原状态且不会覆盖后续操作；不能为方便返回“失败”而写回旧授权。删除已完成的 MO Role 不能通过重建空 Role 伪装成回滚。

#### 重试、并发与人工处理

- 执行锁、租约、进度和有界重试预算复用[现有 Saga 执行器](../../moi/pkg/components/saga/executor.go)及[持久恢复接口](../../moi/pkg/components/saga/storage/storage.go)。只重试合同明确允许的阶段；查询结果、重放请求、进程重启和人工核验均不重置原预算。确定性业务拒绝不自动重试。
- 同一 Role 上仍在执行或无法确认已停止的权限操作，必须隔离冲突的后续权限写入、编辑和删除；其它 Role 正常操作。Saga 锁只协调同一 operation，不能代替目标 Role 的并发保护。整角色编辑在持久失败终态确认后释放原请求占用，允许用户重新编辑；失败记录保留，原操作不能重新执行或覆盖后续保存。独立数据权限操作的投影修复按第 6 节处理。
- 新用户请求重新鉴权、解析当前目标身份并校验版本。恢复使用原操作的冻结身份与目标，凡是执行新的授权副作用，仍需满足该业务现行准入合同；持久 intent 本身不授予权限。纯粹确认已提交结果不应重新制造副作用。
- 普通保存只执行本次输入，不接管旧操作、不合并旧操作的结果。中断恢复统一进入已有共享 Saga 入口，由原 owner 显式登记恢复方法，按操作类型领取未完成记录，取得原执行权并使用剩余预算；不扫描全部 workspace、不抢占活跃执行者、不复活失败终态。角色删除的恢复约定见第 4.2 节，整角色编辑见第 4.3 节，独立数据权限见第 6 节。
- 数据权限人工修复重新鉴权，并校验原操作、Role、资源稳定身份和版本；只把 MO 当前事实同步到 MOI，不重放历史授权。旧失败 intent 和审计保留；修复回执、版本、投影、审计和解除占用必须在同一本地事务提交。无法安全解释的原生行列规则保留为观测事实，不能伪造为可编辑草稿。
- 失败记录按业务类型、workspace、目标、operation/request/trace ID 可查询，并记录执行阶段、尝试次数、原始错误和读回结果。“原执行失败”与“后来已处理”分别保存，后者必须有正式业务完成证据；不能直接改成功状态、清空错误或重开预算。有限重试仍不一致时，由业务 owner 和有权管理员通过正式修复能力处置；操作已经过时或被后续保存取代时，按当前事实核验，不能执行旧授权。统一 Saga 人工介入接口和后台管理另行提供，本次不新增管理框架或整角色完成接口，也不以人工处理作为下一次保存的前置条件。

#### 建库权限派生同步

Catalog 删除清理最后一条建库授权时，`ApplicationPolicyPrivilegeProjection` 在独立 System 存储中先持久化 `iam-database-create-projection` Saga，再撤销 MO `CREATE DATABASE`。Catalog、Policy、Ownership 仍在原 tenant transaction 内共同提交或回滚。已确认提交后由真实事务 owner 直接以 CAS 完成 Saga，不再读取 tenant 或执行 DCL；完成写入失败先读回确认，仍不能确认时返回错误并保留原 intent。已确认回滚后由真实事务 owner 触发恢复；提交结果不明、收尾未完成或进程中断时，由公共 IAM Saga 恢复入口接管。恢复持有目标 Role 行锁，在获锁后新建读快照，按当前已提交策略及 Role 状态幂等同步并 readback DCL；不重放 Catalog 删除、不按旧快照无条件重新授权，也不重建已删除 Role。正常成功记录不进入后台恢复；完成 CAS 不得覆盖已有的恢复执行锁。恢复沿用持久重试预算，耗尽后保留 `failed` 和错误；同请求不得重开终态预算。

SQL 历史复用同一投影 owner 与 Saga：`query_history.read` 的授予在 Policy 提交后物化 SELECT，撤销先完成 REVOKE 再提交 Policy；两者都在首次副作用前保存原操作 intent，恢复只依据当前已提交策略。整角色编辑复用该编辑自身的 Saga，避免另建投影操作。旧 `query_history.audit.read` 只作为已发布策略别名解释为 `query_history.read`，权限编辑器不再展示独立选项。已有角色缺失的 SELECT 由 offset189 在租户准入前一次性补齐，沿用升级账本和验证，不增加运行期全租户权限扫描。

### 4.1.1 角色继承修改

MOI 完成工作区准入、Core 权限校验、父子角色 lifecycle 检查和操作留痕。MO 负责继承关系保存、GRANT/REVOKE、防环与并发一致性。MOI 不在继承写链路读取全图进行版本互斥、防环或规模检查。

执行顺序：准入 → 按角色数值 ID 升序锁定父子行 → 校验角色当前状态 → 独立提交 `pending` → 一次 MO DCL → 记录明确结果 → 释放角色锁。角色锁覆盖 DCL 与结果记录，协调同角色的修改、禁用、删除；不同角色对可并行。独立连接避免日志提交或 DCL 被持有角色锁的事务回滚。最初日志写入未确认成功时不调用 MO。

| 状态 | 已知结果 |
| --- | --- |
| `pending` | 尚无完整最终结果，可永久保留，不占用工作区或角色 |
| `resolved` | MO 明确成功，且该结果已写入操作日志 |
| `failed` | MO 明确拒绝，且失败已写入操作日志 |

超时、断连、取消和进程中断保留 `pending`。MO 明确成功后，结果日志、附加审计或释放锁失败仍返回成功，并记录包含 workspace、父子角色、操作者、请求编号、阶段与原始错误的结构化系统日志。不回滚继承，不读回推断并补执行，也不重新鉴权恢复旧操作。原始 MO 错误仅进入受控日志；API 提供稳定 code 与安全的本地化文案。

同工作区的 `request_id` 唯一。相同输入重复提交只返回原结果；更改输入复用编号返回冲突。历史成功不会因当前边已删除而重新授权；历史失败不会因状态改变而重做；历史 `pending` 只返回未确认。用户主动再次修改使用新编号并重新准入。

读取旧记录时，`prepared`、`external_applied`、`recovery_required` 解释为 `pending`，`succeeded`、`rejected` 分别对应已知成功和失败；保留原始记录，不制造终态。角色删除忽略所有继承操作日志；当前继承边不阻止删除，由 MatrixOne `DROP ROLE` 清理。

上线必须先停止、排空旧版本的继承恢复执行器与在途继承请求，再启用新版本写入口。禁止旧恢复进程与新写入口混跑；新版本已删除继承扫描和定时调度接线，重启不会处理历史继承日志。其他 IAM 恢复器继续正常运行。MO 4.2.6 并发授权成环由 [MatrixOne #31677](https://github.com/matrixorigin/matrixone/issues/31677) 跟进，MOI 不增加补偿性防环逻辑。

### 4.2 Role 删除

首次执行通过既有 Saga 执行器原子发布完整意图与运行租约，再以该执行 fence 进入删除步骤；不能先暴露可由恢复器领取的 `pending` 记录。相同请求并发创建时只读取已存在操作并校验原 payload hash，不领取或重做竞争者的执行。活跃请求仍由原执行器维护心跳，进程中断后才按既有恢复合同接管；该协调不替代下述 Role 行锁与当前权限校验。

Role 删除的终态是 MatrixOne Role 和 MOI 普通 Role 均不存在，原请求的成功回执与审计仍可读取。MatrixOne DCL 与 tenant 元数据分别提交，不能假设跨两者原子回滚；中断恢复必须读回已提交事实并完成剩余清理，不能重新创建空 Role 来补偿已经丢失的数据权限。

`iam-role-delete` forward-only Saga 是唯一执行状态源，在首个副作用前保存完整请求、canonical actor、Verified Effective Role、request/trace 与 payload hash，统一负责重试、预算、心跳和执行接管。业务只提供一个幂等删除 step。新请求不再在 tenant 账本另写 `prepared` 或复制恢复意图；tenant 账本只在最终事务中保存成功结果。历史 pending 记录按原身份校验，已有 Saga 可继续原位收尾；没有 Saga 的历史未完成账本保持只读未知结果，不由普通重放自动接管。

一次执行在同一 tenant transaction 中锁定相关 Role，校验目标版本、provisioning ready 及有效版本、系统保护、binding、Default Role 和未完成权限操作，并在同一事务中验证全部 Ownership 与接收角色，再确认旧 MatrixOne Role 是否存在。创建、编辑或补偿尚未完成的目标不能删除，以免与其外部 DCL 及原操作收尾冲突。仍存在时，原 actor 必须有效；恢复执行还必须通过正式身份目录解析原 canonical actor，并以冻结 Role 重新进入生成的 `GetDeleteImpact` / `role.delete` 边界，才能执行 DCL。已确认 MatrixOne Role 缺失且无需转移时，只继续原请求的本地收尾。转移是新增授权，首次执行、同进程自动重试与重启恢复的每次实际转移都必须重新校验原 actor、冻结 Role、`role.delete` 和 `role.update`；重验清除旧请求的授权快照，不能借 MO 缺失跳过准入。目录、存储或 MatrixOne readback 失败仍返回错误，不能当作授权撤销或物理缺失。

删除条件在持锁后完整检查，最终写入继续用原 Role 版本 CAS；前述生成边界的重新鉴权仍校验当前删除影响。Role 行锁覆盖 DCL/readback 与本地收尾，DCL 本身通过独立 autocommit 连接执行。Saga 执行锁只协调同一操作，不能阻止 binding、Policy、Data Privilege 和 Ownership 写入，因此本次不以 Saga 锁替代 Role 行锁，也不新增 `deleting` lifecycle 与全调用链写入协议。

删除进行中保留原 Role 行、版本和持久化意图，继续使用既有行锁与 CAS。确认 MatrixOne Role 已不存在后，最终 tenant transaction 先完成所需的 Ownership 转移，再硬删除普通 Role 主表行及其运行期授权元数据，同时提交删除成功回执与审计；任一步失败均回滚本地事务。清理范围包括该 Role 的 binding、Default Role、Policy 文档与授权索引、Data Privilege 当前状态/版本/锁；Ownership 按接收角色保留，不随源角色删除。删除前对 binding、Default Role 和未完成业务 operation 的阻断检查不变；清理不是绕过这些检查的入口。继承关系不阻止删除，删除预检和最终删除校验不统计继承数量，删除弹窗不展示继承提示；MatrixOne DROP ROLE 清理目标参与的全部继承边，成功后 canonical Role graph 不再包含这些边，相关角色失去沿这些路径继承的权限，包括经目标角色传递的多层继承权限。无需逐一重写其他角色的策略，其他直接授权及有效继承路径保留。其它角色已创建的业务对象及其 Ownership 保留。历史 operation、审计及决策记录保留，不因 Role 主表删除而丢失。

独立 Data Privilege 的 `applying` 操作计入删除阻断。Data Privilege prepare/finalize 在写入版本或权限状态前取得同一 Role 行锁，并确认目标 Role 仍存在且非 deleted；普通持久操作保留原有生命周期准入，不因本次新增删除 fence 扩大拒绝。角色物理缺失或历史 deleted 墓碑仍拒绝。角色创建、编辑及其补偿继续验证原 request fence，不得在 Role 已物理删除后重建权限元数据。

管理界面的分批转移复用独立 Owner mutation，每页读取 10 条，逐对象短事务提交 CAS、审计与幂等回执。后续对象失败不会回滚先前成功事务；前端显示已确认完成数量，停止后续写入，角色保留。结果未知的对象只允许按原请求 ID 和冻结参数显式重放确认。分页全部处理成功后，前端发起不含转移方案的独立 DELETE；如果期间又有对象或绑定，删除校验拒绝，已完成转移仍保留。不新增持久化批次、版本标记或恢复任务。

现有公开删除请求仍可以携带 `ownership_transfer`：选择一个 `target_role_id` 接收全部对象，或通过 `targets` 逐对象指定接收角色；两者互斥，逐项方案必须完整覆盖源角色的有效 Ownership。`expected_ownership_version` 来自完整集合，不使用有限样本计算；资源新增、移除、版本或状态变化均使旧方案冲突。接收角色必须属于当前租户、active 且 provisioning ready，可包含受保护的 `admin`/`superadmin`，但不能是被删除角色。角色删除本身仍保护系统角色。

Actor、被删除角色及全部接收角色按 ID 升序一次锁定，随后锁定 Ownership。最终 tenant transaction 先按版本 CAS 转移 Ownership、递增版本、保留创建 provenance 并逐项记录原 Owner、接收角色、资源和版本，再完成角色及旧授权元数据的硬删除、成功回执和审计。所有本地写入共同提交或回滚。转移只改变 MOI 应用对象 Ownership，不复制原角色的 Application Policy、成员绑定或 MatrixOne 数据权限；原删除 Saga 冻结转移方案与完整 payload hash，恢复和同请求确认不得换目标或重置预算。

删除回执中的逻辑 Role 仍为 `deleted`，保存旧 Role ID、原名称、描述和生命周期版本；它是历史结果快照，不要求 `roles` 行继续存在。相同请求直接读取原回执并验证 MatrixOne 物理 Role 仍缺失，不能重新定位或删除同名新 Role。审计按旧 Role ID 独立查询。可信 Role 查询确认不存在时作为无效角色拒绝授权；数据库、租户连接或凭据读取失败仍属于依赖不可用，不能伪装成角色已删除。

offset183 清理已经 `deleted` 且 MatrixOne 物理 Role 已不存在的历史普通角色及其运行期授权元数据，按 Role ID 分页并支持幂等重跑。发现物理 Role 残留或读取失败时必须报错，不自动 DROP。旧升级流程保留的系统 Role 墓碑（例如 `empty`）保持原记录。已有历史 operation 与审计不变；缺少历史记录时不编造回执或审计。`roles.name` 保持 `VARCHAR(255)`，不引入内部名称归档格式或列扩容。

新建同名角色必须分配新 ID，不能复活旧身份或继承旧授权。active、disabled 及尚未完成创建/回滚的普通 Role 继续占用名称。名称唯一冲突保持 `409 ErrIAMRoleNameExists`；Role 硬删除或必需清理失败属于原删除操作的失败，不能返回删除成功。

该 owner 启用 `PersistRetryBudget`，首次执行后最多自动重试 3 次，已开始的中断尝试占用持久预算。请求取消、父上下文超时或停机中断保留未完成 Saga 及检查点，恢复只使用剩余预算；重试等待期间尚未开始的下一次执行不计入预算。step 自身超时仍按执行失败处理。预算用尽或确定性业务拒绝后，保留 `failed` Saga 和完整错误日志；同 request 重放原失败分类，新 request 是独立的显式操作。若 DCL 已成功而 tenant 收尾失败，本地 Role 可能仍为 active；保留原本地事实和诊断，不能把失败结果解释为权限已恢复。公开错误与前端处理见[公开合同 §6](07-public-api-frontend-sdk-contracts.md#6-ownership-impact-与-role-删除)。

`SagaRecoveryRunner` 将 Role 删除、整角色编辑、Catalog 建库权限投影与独立数据权限共用一个恢复入口，复用现有 Mowl `ScheduledScanRetry` 和 IAM 恢复间隔，在监听启动后执行一轮，每轮结束后再等待配置间隔。每次从 System Saga 表合并领取这些类型中最多 100 个 `pending` 或 lease 已过期的 `running` 操作，再通过各自正式生成 Service 分发；只有持久任务指定的 workspace 会被访问，不枚举全部 workspace，不为每种 Saga 新增周期任务。部分领取失败仍处理已经领取的任务，一个领域恢复失败也不能丢弃另一领域已领取的任务。使用既有 `ClaimRecoveryBatch`、fenced 状态转换和同一 Saga builder 重建 action，再由执行器接管；活跃执行者不被抢占，`failed` 在候选查询和重新读取时都排除，预算不重置。

tenant 成功账本先于 Saga 完成状态落盘的中断，由 step skip-check 在重试预算检查前识别；确认同一请求的成功回执和旧 MatrixOne Role 缺失后，只完成 Saga，不重做已提交事务。成功重放也必须确认旧 MatrixOne Role 当前缺失；查询失败或 Role 重现时返回既有结果未知错误并记录完整诊断，已完成请求不重开预算，也不自动删除重现的 Role。

### 4.3 Role 创建与编辑

Role 创建沿用租户内的暂存事实与操作回执，不再创建 system Saga。失败时先确认新建 MatrixOne Role 及其 DCL 已清理，再由本地事务删除暂存 Role、Policy、Grant Index 和数据权限事实；无法确认外部清理时保留未完成状态。完整产品合同见[公开合同 §3.1](07-public-api-frontend-sdk-contracts.md#31-role-创建)。

整角色 PATCH 由 `roleProvisioningService` 负责。名称、备注、Application Policy 的写入与版本、审计和成功回执共用一个 tenant transaction；请求未携带数据权限 mutation、策略派生的 account `CREATE DATABASE` 与 `system.statement_info` SELECT 要求均未改变时，不创建 Saga、不访问 MO DCL。读取旧 Policy 只用于判断这一外部权限边界，不能用于跳过普通保存。相同设置以最新版本再次提交也执行保存、推进版本。

确需修改 MO 时，只使用一个 `iam-role-provisioning` 聚合 Saga，保存完整请求、编译后的 Policy、数据权限稳定资源身份和冻结的 actor／Effective Role。首次执行由现有执行器先取得运行租约，再持久化意图和步骤，避免共享调度器抢占尚未开始的新保存。执行顺序为：

1. 在 tenant transaction 内校验 lifecycle／policy／data privilege 三个版本，取得 Role 的原请求占用并提交 `pending`。
2. 执行派生 account privilege 和数据权限 DCL，并读回确认结果。首次执行后的重试或中断接管只读回，不再次执行原 DCL；未开始的旧意图不自动发出授权。
3. 在一个 tenant transaction 内保存 Application Policy、数据权限投影与版本、角色元数据、必需审计和成功回执，最后恢复 `ready`。数据权限 prepare/finalize 复用现有 Repository 并加入此事务；不另建子 Saga、提前提交子操作账本或注册独立恢复入口。

本地提交失败只重试第三步，复用原 Saga 的持久预算。原 Saga 的 `failed` 终态确认落库后，由该 owner 在 tenant transaction 中按原 request 和版本释放占用，将 Role 恢复为 `ready`，保留失败标记与诊断。仍在执行、终态未确认或释放事务失败时保留 `pending`；下一次新保存可以重新确认已停止的原操作并释放它，不重开原预算。释放只改变可编辑状态，不写成功回执，不写回旧 snapshot，不执行反向 GRANT／REVOKE，不能承诺 MO 权限已恢复原状。

失败后的新保存重新鉴权并校验当前版本，只执行用户当前输入；不读取旧 intent 来合并资源、不自动导入旧部分授权，也不因历史失败而额外重设派生 account privilege。新请求明确提交的 mutation 仍可覆盖或撤销同一资源上的旧部分结果。保存前校验 provisioning version，避免跨过并发变化的执行占用；成功后清除 Role 当前失败标记，原 Saga 失败事实保留。若旧操作仍有 MO／MOI 不一致，留待 owner 管理员显式处置；普通新保存成功不代表旧操作已修复。

成功回执复用 `iam_resource_lifecycle_operations`，与全部 MOI 事实同事务提交，保存原请求 hash 和完整返回值。提交响应丢失或后续编辑不会改变该回执；原请求返回其历史成功结果。Saga 终态未落盘时，由共享恢复入口在原执行锁下跳过已提交步骤，只完成 Saga 记账，不重开预算；普通同请求调用直接返回业务回执，不承担这项恢复。已失败的 Saga 保留失败事实，不由重试复活。

中断的旧编辑由 `SagaRecoveryRunner` 领取，回到生成的 `RecoverRoleUpdates` Service 边界，沿用原执行租约、fence 和剩余预算，只读回 MO 并完成原本地收尾。普通新保存和同请求确认都不触发恢复；旧执行尚未停止时保留冲突隔离。恢复若已推进业务版本，新草稿按原版本返回正常 CAS 冲突，刷新后可再次保存。各步骤的确定性拒绝持久保存原错误分类，同请求重放保持该分类。过期恢复 claim 不能跨过新 fence；本地收尾还要通过原请求占用和业务版本校验，不能覆盖后来的成功保存。

聚合 Role 写入中的 Data Privilege 子操作始终由该 owner 负责。独立数据权限读取、核验、repair 不接管它；统一人工介入能力应通过该 owner 按当前事实处置，不重放旧快照、不重开失败预算。

### 工作区成员删除与继续处理

成员删除复用原持久 Saga，先保存稳定请求、原操作者与 Effective Role、membership ID、生命周期版本、账号 ID 和数据库用户名。删除准备不会先写入用户可见的 `deleting` 生命周期；System membership 在系统删除收尾提交前保持原来的 `active`/`disabled` 状态，避免 MO 清理失败时出现“列表已移除但账号仍可用”的假象。

准备阶段的删除审计记录 `deleting / started`，只表示操作已开始，审计版本仍使用删除前的 membership 版本。Saga 依次删除 MatrixOne 数据库账号、清理 tenant 角色绑定/默认角色/资料，最后在一个 System transaction 将原 membership 收尾为 `deleted`、删除 `db_users` 映射并写入成功回执。账号删除失败时保留成员原状态并停止后续步骤；tenant 清理失败时仍尝试最后的 System 删除：System 成功则报告成员删除成功并隐藏该成员，内部保留 `repair_required` 回执、失败 Saga 及详细日志供运维处理，不向用户提供继续删除，也不安排周期重试；System 失败则保留原 active/disabled 状态及账号映射，返回失败供显式继续，已经完成的 tenant 清理不回退。每步确认精确目标不存在时可幂等完成；MO 账号删除与 System 成员收尾均已确认提交才报告成员删除成功，不能将孤儿清理状态伪写为成功。失败时保留系统记录和原请求，返回稳定错误码与安全本地化消息，原始错误链、失败阶段、请求/追踪/Saga 标识进入结构化日志。

用户点击“继续删除”显式接续同一请求和未完成检查点，重新验证当前删除权限、原成员身份及版本；已完成的步骤不恢复原数据。重启恢复仅领取未结束且执行租约已失效的操作，排除最终 `failed`，不为已失败任务安排无限后台重试。新邀请必须等待旧删除清理收尾，存在孤儿绑定时仍需先由运维处理，避免继承旧权限；已成功移除成员的旧删除请求只读重放原回执，不再尝试清理孤儿，也不能删除新 membership 的账号或绑定。同一成员 lifecycle Saga 的启停操作共享中断恢复入口，恢复仍核对原成员版本并要求对应的当前启停权限，不改变其已失败请求的只读重放语义。

### 4.4 用户标签整批替换

用户标签值是 tenant subject attributes。替换由现有 `replaceIAMSubjectAttributeValuesWithExecutor` 在调用者的 tenant transaction 内完成，标签单独更新与 member profile 联合更新共用这一个 writer：

1. 按 canonical `moi_user_id` 删除该用户旧值，不清理其他用户。
2. 非空输入逐项要求正 tag ID 和非空值，然后用一次 `SELECT tag_id ... IN (...) FOR UPDATE` 锁定仍存在的定义；定义查询、扫描或迭代失败即终止事务。
3. 只对本次锁定查询确认存在的定义，执行一条参数化多行 `INSERT ... VALUES`。已删除定义沿用显式跳过并记录告警的语义，不重新创建定义或属性值。

含有效标签的正常批次，替换部分从 `2N+1` 次数据库往返降为 3 条 SQL；空输入只执行删除，全部定义已删除时执行删除和定义查询、没有 INSERT。计数不包含 transaction begin/commit、profile 更新、mutation audit 和返回值 readback。SQL 只拼接占位符，用户值始终通过参数传入；重复的有效 tag ID 不去重或覆盖，由唯一键失败触发整批回滚。

非法输入、定义读取、INSERT 或 mutation audit 任一步失败，都回滚本次删除和写入；联合 profile 更新同样不能部分提交。成功后的返回值仍由原 readback 路径取得，批量 INSERT 不新增忽略写入错误、自动重试或部分成功合同。标签用于新 SQL 连接的签发时机见[SQL Active Role](03-request-runtime-contracts.md#7-sql-active-role)。

实现入口：[subject attribute writer](../../moi-core/catalog/pkg/service/storage/tenant/iam_subject_attributes.go)。

### 4.5 用户角色绑定

用户角色绑定复用持久化 Saga。首次 MatrixOne 副作用前，保存由 workspace 与 request ID 确定的操作身份、原 payload hash、已准入 actor/Effective Role、目标 membership 及版本、完整目标角色集合和旧绑定。Saga 是执行状态的唯一来源，正常绑定不再维护 tenant `prepared`、`external_applied` 或 `recovery_required` phase。

同一用户的变更由业务 owner 串行仲裁，先验证冻结版本及目标 membership，再幂等收敛 MatrixOne 角色授权；绑定集合、默认角色、版本、成功回执和审计在同一 tenant transaction 提交。持有用户锁时，DCL 使用独立的短生命周期管理连接，结束后关闭，避免向已经持有事务连接的同一有限连接池再次申请连接。失败请求的外部残留不能污染后续显式请求的目标集合。成员删除使用同一用户的仲裁边界，不能越过执行中的绑定变更删除数据库用户。

恢复复用 Saga 的执行锁、lease、有界重试预算和失败终态，只从全局 Saga 存储领取未完成任务，不定期遍历 workspace。可从持久状态重建的执行定义只在当前执行期间保留，不随历史请求持续留在常驻执行器中。成功回执优先于旧执行状态：同一请求返回原结果，后续请求已经改变的绑定与 MatrixOne 授权不因旧请求重放而恢复。确定性拒绝或预算用尽后，同 request 不重开执行；新的显式请求使用新 request ID。

旧 tenant intent 只做一次接续导入。确认相同操作的 Saga 已持久化且身份、原 hash 和冻结事实一致后，才能移除旧 intent；所有历史候选处理完成后持久化全局完成标记，后续启动不重复枚举租户。切换前须排空旧版本的绑定写入，避免完成标记之后仍产生旧格式操作；读取、导入或 checkpoint 失败不得冒充迁移完成。

一次性导入使用同一个固定 Saga 标记和执行 lease，每次恢复回调至多执行一轮。迁移依赖暂时不可用时保留原意图和错误，下一回调或进程重启后继续，执行 fence 与结构化日志保留每轮事实；该基础设施任务不消耗普通用户绑定命令的终态预算。冻结数据无效或 payload hash 冲突属于确定性失败，持久化原因后停止重做并继续报告诊断。只有重新读取到同一执行 fence 下的持久化完成标记，才能确认本轮导入完成并解除后台失败。

## 5. 邀请接受

邀请创建和接受必须保留以下 durable facts：

- canonical target user ID；
- inviter/actor 的可信快照；
- assigned Role IDs 和显式 Default Role ID；
- acceptance operation、phase、request/trace ID；
- MatrixOne username；
- 在完成 readback 前可恢复的加密凭据。

接受流程使用同一邀请 ID 标识的持久 Saga，依次提交 tenant Role/profile/default、执行并读回 MatrixOne user/grant，最后在同一 system transaction 内提交 membership、db user 和 invitation 完成状态。全部完成后才返回接受成功，不提前激活成员。

邀请不再注册周期性恢复任务，也不加入共享 Saga 的后台领取集合。每次显式接受使用现有 Saga 执行锁，从未完成步骤继续；重试次数、间隔和退避均沿用 Saga 统一配置，由执行器管理。预算耗尽后保存失败检查点与结构化诊断并返回错误。失败邀请仍以 `accepting` 展示，受邀者可通过原接受接口再次执行；上一次失败不封锁新的显式接受。已持久化成功的 tenant 或 MatrixOne 步骤不重新执行，因此 MatrixOne 成功而 system 提交失败时，再次接受只补 system 事务。自动接受使用相同链路。

请求取消且执行器已结束时，使用原执行 fence 持久化失败，允许下一次显式接受立即继续，不释放其他执行器的租约。进程重启后由下一次显式接受读取原 Saga 继续，不依赖原进程内的执行定义；尚未结束或崩溃后租约尚未过期的执行仍保留并发隔离。未能持久化成功检查点的步骤按原 intent 幂等重做；同一 MatrixOne user 始终使用邀请中持久化的凭据，不能重新生成或替换密码。已接受邀请直接返回原结果，不因成员之后修改角色或被删除而重放初始授权。

新邀请在准备接受时固定新的 membership ID；已删除成员关系不决定该 ID。完成接受时，在同一 system transaction 内移除已完成删除清理的旧成员行、创建新成员行并提交邀请终态，新成员的 lifecycle version 从 1 开始。旧成员的操作回执和审计保留原 ID，独立于当前成员行读取。仍未完成的删除清理必须先收敛，不能让其后续执行删除新成员的数据库身份或角色绑定。同一邀请的恢复使用已持久化的 ID，不在重试时重新生成。

canonical member、Role binding、Default Role 和 invitation 状态的审计写入失败时，业务流程 fail closed。手机号、邮箱、GitHub login、`uc_sub` 或 Backend uid 不进入 Core 邀请事实；UC 查询失败不产生挂起邀请。

## 6. Data Privilege durable operation

独立 Data Privilege apply 遵循第 4.1 节的跨事务标准：先执行并确认 MO，再提交 MOI 权限投影、版本、回执和审计。正常请求直接执行本次 DCL，再做写后读回；不先读取整份权限来判断是否需要执行。`clear` 只在 MatrixOne 协议需要时检查目标规则是否存在。

apply 的业务 `request_id` 可省略，由后端生成并返回；每次省略编号都是新的保存。显式提供编号时，以原 `request_id` 和 canonical payload hash 识别同一请求，不同 payload 冲突。`expected_data_privilege_version` 使用目标 Role 的独立版本表做 CAS，不能从明细 state 行反推；省略请求编号不取消版本校验。

对象级 `table.grant.*`/`database.grant.create_table` 目标通过 data-privilege 接口执行；当前 Verified Effective Role 具有 workspace `role.create` 或 `role.update` 时可管理任意对象，没有该权限时只有 canonical active exact Owner 可按 WGO 语义委派自己的对象。`with_grant_option=true` 时还必须在 MatrixOne 写后读中确认对应对象事实的 `WITH GRANT OPTION`。

独立操作复用 `iam-data-privilege` Saga 的 MO 执行／读回与 MOI 提交步骤，MOI 提交使用持久化有限重试预算。首次执行由既有执行器先原子创建运行租约，再持久化 intent 和步骤，完成前不执行业务写入；不先暴露可被恢复器抢占的 `pending`。中断恢复接入已有 `SagaRecoveryRunner` 的有界 System claim 批次，由原 owner 处理；不新增独立扫描器，不枚举 workspace，不领取活跃执行或失败终态。恢复核对持久 intent、operation ID 和 payload hash，沿用原执行锁和剩余预算，只读回已提交的 MO 事实，不因旧目标尚未达到而继续执行旧 DCL；执行尚未停止时保留同 Role 的冲突隔离，不能将响应超时当作执行已停止。MO 已完成后的本地收尾锁定 Role 并验证原 operation、payload 和版本，不重建已删除 Role，也不把原 actor 后来失权解释为已经完成的 DCL 被撤销。

公开状态为 `applying`、`succeeded`、`failed`、`drifted`、`unknown`；非成功结果仍保留 operation、data privilege version、MatrixOne fact version、session invalidation status 和逐资源结果。`unknown|drifted|failed` 是已停止操作的历史结果，不阻止后续独立权限保存、整角色编辑和删除。`applying` 保留并发隔离；若其 Saga 已持久化为 `failed`，由原 owner 在返回失败或下一次编辑时将遗留回执原子收束为 `unknown`，记录审计并释放占用，不修改权限投影或递增数据权限版本。确认终态失败前不得释放占用，不能仅凭等待时间解锁。新保存使用当前输入和版本；旧操作的回执状态检查与版本 CAS 阻止延迟收尾覆盖新操作。手动 repair 是可选的当前 MO 事实同步，不是继续编辑的前置条件；中断操作仍由共享恢复入口接续核验，不增加第二套扫描或恢复逻辑。

Drift readback 和普通 GET 只诊断，不自动修复或覆盖 MO。session invalidation 只能报告已证明的事实；无法证明全部旧 session 刷新时使用 `new_connections_only` 或 `unknown`，不能声称全量生效。整角色编辑的数据权限子步骤由第 4.3 节的聚合 owner 处理，不另建独立 Saga；本地验证范围以[实现状态](05-implementation-status.md)为准。

升级前持久化的独立 `applying` 回执可能没有 Saga。仅对包含旧字段 `RoleWriteCompensation:false`、且完整 intent、原 hash 与操作身份校验通过的历史记录，新保存只调用现有释放入口将历史回执记为 `unknown`，不导入旧权限、不推进数据版本；原 intent/hash 保留，显式 repair 继续可用。普通同请求调用只返回已确认结果或进行中冲突，不承担恢复。新格式记录缺少 Saga 时仍报依赖不可用，不能将存储缺失解释为执行已停止。升级切换须先停止旧版本写入；时间长短不作为安全解除占用的依据。

Database 物理删除确认成功后，Database owner service 必须在删除 Catalog 元数据的同一 tenant transaction 内，按 `catalog_table.database_id` 集合清理该 Database 与全部子 Table 的 `iam_data_privilege_state`，并将每个受影响 Role 的 `data_privilege_version` 只递增一次。该清理必须先于 `catalog_table` 删除，不能逐 Table 发起 SQL，也不能在 Ownership registrar 中做删除后的补偿。MatrixOne `mo_role_privs` 中若仍残留已删除对象 ID，只能作为不可用历史行忽略；权限视图必须通过当前 `mo_database`/`mo_tables` 对象事实过滤，不能把残留行解析为授权，也不能因此返回 500/503。同名 Database/Table 重建后使用新的对象身份，旧行不得重新生效。

## 7. 审计

IAM mutation 和授权决策分别记录可追踪事实。审计至少包含：

- workspace、event/decision type；
- actor principal 和 actor active Role；
- target type/ID 或 resource/action；
- operation/request/trace ID；
- policy、Ownership、Role graph、data privilege 和 lifecycle version；
- decision、reason code、matched statement/grant/owner hit；
- 脱敏后的 payload summary 和时间。

邀请接受的 actor 来自 invitation 中的可信快照；Role 和成员审计只走 Core `iam_audit_events`。列表按时间倒序，默认分页大小由公开契约统一维护，不能由 UI 和 Core 各自推断。

Core `Authorize`/filter 的 decision audit 使用 `IAMAuditSink` 尽力持久化；写失败必须记录结构化错误，但不能改变已经计算完成的 allow/deny，也不能用 `ErrIAMAuditUnavailable` 覆盖原始拒绝或依赖错误。IAM mutation audit 由 owner transaction 或 durable operation 与业务事实一起提交，写失败仍然不能报告 mutation 成功。`IAMDecisionRecorder` 是 best-effort 决策摘要；它和 decision audit 都不能成为授权事实，也不能替代 mutation 的事务内审计。

## 8. 升级与 hard removal

当前 legacy hard removal 的实现位于 Offset110：

- fresh-install schema 与 upgrade handler 必须保持一致；
- 一个 PR 只使用一个当前未合并 offset；若 offset 被 upstream 占用，整体顺延，不能修改已合入 offset；
- owner/member seed、system Role、Default Role 和 profile reconciliation 必须同时覆盖 fresh tenant 与 latest-1 -> latest；
- 不迁移历史自定义 Role、旧协作者 binding/default/policy/继承，也不恢复旧权限表；
- canonical workspace 级 subject-attribute 定义按当前升级合同保留，已删除历史协作者的属性值不迁移；无法可靠映射 owner 身份时 fail closed；
- Offset110 只能依据首次 system transaction 持久化的 reset snapshot 删除外部事实：非 owner `db_users`、具有持久 `acceptance_db_username` 的 pending/accepting invitation，以及受管理命名空间中可 readback 的旧 MatrixOne role/user；
- `users.username`、当前请求身份、system owner 或缺少 durable username 的 invitation 不能作为 MatrixOne 用户删除证明；owner 产品 SQL 用户和内部 owner 用户必须受保护；
- 清理后必须 readback user、role、user grant、role grant、privilege 和 row rule。任何残留或无法证明的终态都使升级 fail closed，只有事实收敛后才能清理 invitation 凭据和 reset snapshot；
- 未完成的 legacy durable operation 必须进入不会再被 recovery worker 扫描的明确终态。

Offset 号和实际 SQL 是实现事实，修改前必须重新读取 `moi-core/catalog/pkg/upgrade/AGENTS.md` 及当前 upstream，不能从本文推断下一个 offset。

## 9. Recovery 可观测性

Recovery 必须记录结构化 operation、phase、workspace、resource、request/trace ID、attempt、分类错误和 readback 结果。永久错误进入明确终态并告警；瞬时错误按 owner service 的有界策略重试。

scanner 只能拾取有恢复语义的状态。升级终结的 legacy operation、已完成且 readback 一致的 operation 和永久拒绝不能形成无限轮询。
