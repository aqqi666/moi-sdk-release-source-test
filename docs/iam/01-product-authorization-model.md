# MOI 产品与授权模型

本文定义 MOI 应用权限的规范性产品模型。这里回答“谁以什么角色对什么资源执行什么动作”，不记录阶段计划，也不描述某条 route 当前是否已接入。查询当前业务功能/API 对应的 action、授权层级、Ownership 和依赖资源时，阅读[业务功能权限模型目录](08-business-permission-model-catalog.md)；核对 Registry 代码集合或当前例外时，阅读同前缀的[Registry 快照](09-business-permission-model-registry.md)与[例外登记](10-business-permission-model-exceptions.md)。

## 1. 目标

MOI 权限系统必须同时满足：

- 用户在一个 workspace 内只能以一个当前、有效、可审计的 Role 执行业务动作。
- 普通 Role 的应用对象权限与 MatrixOne 数据权限边界清晰；`admin`/`superadmin` 是显式初始化的系统最高权限 Role，在 MOI 和 MatrixOne 中都具备完整的产品权限。
- point authorization、集合过滤、异步执行和恢复使用同一套 canonical facts。
- 无法证明授权时不放行；可控的授权异常按无权限处理并限制影响范围，其它已独立获权的功能继续可用。错误分类与诊断遵循第 9 节。

## 2. Principal 与身份

### 2.1 Canonical principal

MOI 应用 IAM 的用户主键是 Core `moi_user_id`。`uc_sub`、Backend uid、手机号、邮箱和 MatrixOne username 都不是 Core 用户管理、邀请、Role binding 或授权事实中的 principal ID。

Backend 负责将已认证账号或已验证手机号解析为已有的 canonical `moi_user_id`，再调用 Core。无法唯一解析时返回稳定业务错误，不能猜测两个 ID 相同。

### 2.2 Role Candidate

Role Candidate 是调用者希望使用的 Role，只是输入，不是授权结果：

- Backend 外部 API 可以从受信 transport 读取 Explicit Role Candidate。
- 未显式提供时，Backend 可以把 Default Role ID 作为候选，但不能因此直接 allow。
- Core 必须验证候选属于同一 workspace、对当前 principal 是 direct binding，且 user、membership、Role、binding 和 workspace lifecycle 均有效。
- 候选无效时拒绝，不回退到其它 binding，不做角色并集，也不选择“权限更高”的 Role。

### 2.3 Verified Effective Role

Verified Effective Role 是 Core 对候选完成验证后得到的唯一当前 Role。一次业务裁决只能使用一个 Effective Role。

以下事实均不能单独替代 Verified Effective Role：

- 用户已登录或拥有 `moi_user_id`；
- 用户曾绑定某个 Role；
- 用户拥有多个 Role 的权限并集；
- Default Role 的本地缓存或数组第一项；
- Backend/Catalog/Worker 的 system credential；
- 资源的 system owner 或创建人字段；
- 提交任务时保存的旧 allow 结果。

已登记的 durable execution contract 可以保存创建时由可信 workspace 入口确认的 owner privilege-class。它是绑定到原 task/job 的准入快照，不是普通 Role 的旧 allow，也不能由上述任一事实推导。

## 3. Role 模型

### 3.1 普通 Role

普通 Role 的创建、Application Policy、Role graph、scope、condition、Ownership 和 specific grant 由 Core canonical IAM 管理。产品 UI 仅在 IAM context ready、角色导航可见且 `role.create` capability 为 true 时开放创建入口。`role.create` 包含设置新 Role 的初始 Application Policy 和 MatrixOne Data Privilege；统一编辑只要求 `role.update`，不叠加其它角色管理权限。对象授权和数据权限委派均允许 `role.create` 或 `role.update` 独立准入。一次创建请求必须携带用户选择的初始权限，Application Policy 与 Data Privilege 至少一项非空；只有本地 Role、完整初始策略、MatrixOne Role/GRANT 与 Data Privilege 全部完成并成为 `ready` 后才返回成功。任一步失败都返回创建失败并由 Core 补偿，不向产品层暴露半成品 Role。Frontend 不从本地状态推断 allow，也不轮询、重试或重建内部 provisioning 的初始权限草稿。

### 3.2 `superadmin`

`superadmin` 唯一对应 workspace owner：

- 只有 owner 可以直接绑定并设为 Default Role。
- 不能赋给其他用户，不能继承，不能编辑、删除、启停或修改 policy。
- 同步请求中，当且仅当它是当前 Verified Effective Role，且 Core 已验证 owner、direct binding 和 lifecycle 时，对 Application IAM 全资源 allow。
- durable task/job 创建时已经过可信 workspace owner 判定的，可以同时冻结 `IsWorkspaceOwner` privilege-class；执行、重试和恢复只在该 task/job 内延续该准入，不在中途重新选择 Role 或重新判定 owner。
- 工作区初始化同时为对应 MatrixOne Role 物化完整的产品数据库、表数据面权限；SQL Active Role 仍是 MatrixOne 执行时的实际身份。

### 3.3 `admin`

`admin` 可以由普通成员 direct binding、解绑并设为 Default Role：

- 不能编辑、删除、启停、修改 policy 或参与 Role inheritance。
- 可以被多个成员拥有。
- 当且仅当它是当前 Verified Effective Role，且 Core 已验证 direct binding 和 lifecycle 时，对 Application IAM 全资源 allow。
- 工作区初始化同时为对应 MatrixOne Role 物化完整的产品数据库、表数据面权限；该权限不是普通 Role 的 DCL 继承规则推导出来的。

系统 Role 在存储和公开 API 中都使用同一个英文稳定名称；切换界面语言时名称不变，也不存在本地化显示名层。Core i18n/display mapping 只投影描述文案，不能改写 Role 名称或参与授权事实。

普通 Role 的继承关系不阻止删除，删除弹窗不展示继承提示。删除时清理该 Role 参与的全部继承边，相关角色失去经该 Role 继承的权限。其它角色已创建的对象及其 Ownership 保留，后续访问按删除后的有效权限重新裁决。用户绑定、Default Role、系统角色保护、未完成操作及源角色自身 Ownership 的转移要求仍按[Role 删除合同](04-storage-lifecycle-audit.md#42-role-删除)校验。

## 4. 授权对象

一次 Core 授权至少包含：

| 维度 | 含义 |
| --- | --- |
| workspace | 权限事实所属租户边界 |
| principal | canonical 用户或受支持的非人主体 |
| effective role | 当前唯一 Verified Effective Role |
| resource type | Core Registry 中的 canonical 资源类型 |
| resource ID | owner service 解析的稳定资源标识 |
| action | Core Registry 中的 canonical action ID |
| scope/condition | policy 允许的资源范围与条件 |
| lifecycle | user/member/role/binding/resource/workspace 当前有效状态 |

请求中的名称、路径、creator、frontend state 或未校验 workspace ID 不能直接成为资源事实。PEP 必须通过 owner service 解析可信 resource/workspace/parent。

## 5. Policy、scope 与 grant

- Application Policy 描述 Role 对 canonical resource/action 的允许范围，由 PAP 校验和写入。
- 普通应用对象的创建和查看是当前 workspace 内的全局能力，角色编辑器只提供“无权限”和“全部（`all`）”；不支持向其他 Role 仅开放某个普通应用对象的查看权限。Catalog 数据树是例外：Database、Volume、Table 的查看可细化到指定对象；创建授权的是父容器内创建同类子对象的能力，不是尚不存在的子对象，也不能将某个父容器的授权扩大到整个 workspace。Database 创建以 Catalog 为父 scope，Volume 和 Table 创建以 Database 为父 scope；Table 的查询、行列规则及建表能力对齐 MatrixOne 权限。使用、执行、修改、删除继续遵循各自合同。
- Database 创建的 Catalog 范围只约束 MOI 创建入口。任一有效 Catalog 建库授权（指定 Catalog 或 `all`）都会向对应 MO Role 物化账号级 `CREATE DATABASE`；SQL 直连与 SQL Editor 可以在当前 MO Account 内建库，不受 MOI Catalog 范围限制。MOI 入口仍按请求的父 Catalog 鉴权；两种入口均由当前有效 Role 执行 DDL，MO 物理 Owner 与 MOI 登记 Owner 保持一致。
- 知识库创建要求 `semantic_model.create` 与关联数据库父 Catalog 的 `database.create` 同时成立；知识库创建权限不单独授予 MatrixOne 建库权限。Application Policy 的物理权限投影仅包括 Catalog 建库与查询历史读取两类。
- SQL 历史统一使用 workspace `query_history.read`。我的历史与工作区历史仅是查询分类，不是独立权限；获授权的 Role 同步取得 `SELECT ON TABLE system.statement_info`，撤权同步撤销。MOI、SQL Editor 和直连均允许该 Role 读取同一 MO Account 内其他用户的历史，account 隔离保持不变。跨事务同步复用 IAM 持久 Saga 和有界重试；失败终态保留操作、角色、请求、阶段及原始错误供人工处理，不另设周期性权限重刷。
- 对当前 workspace 本身的 exact 授权仍表示该 workspace 的全局能力，不是指定业务对象；客户端将它显示为“全部”。Ownership 仍可为 Owner 增加自己对象的既有能力，但不产生将全局创建/查看转授为 exact grant 的例外。
- Core PDP 在运行期读取已发布 policy、Role graph、Ownership、specific grant 与 lifecycle facts 做裁决。
- create 动作授权父容器，而不是尚不存在的目标对象；和其它普通 action 一样，create 可以沿有效 Role graph 继承。只有 `admin`/`superadmin` 作为 protected system Role 不参与继承。
- grant action 是被配置到目标 Role 上的能力描述，不是调用者进入委派接口的第二把权限锁。当前 Verified Effective Role 通过 workspace `role.create` 或 `role.update` 时，可以管理任意对象权限；没有该大权限时，canonical active Ownership 只对同一 exact 对象提供对象级 WGO 例外。目标 Role、grant scope、grant option 和策略结构仍必须由 Core 校验。
- Role inheritance 只能影响普通 Role，不能让 `admin` 或 `superadmin` 被继承。

### 5.1 授权能力与使用能力

授权能力规定当前 Verified Effective Role 可以向哪些目标 Role 配置哪些权限；使用能力规定该 Role 当前可以执行哪些业务操作。两者分别裁决，授权结果不要求是操作者当前使用权限的子集。

操作者通过 Core 的授权准入后，可以在该能力允许的对象、action 和 scope 内向其他普通 Role 或自身授予权限。目标 Role 因此获得操作者原先没有的业务能力，属于授权能力的预期结果；不因为目标是自身、权限增加或数据限制减少而追加拒绝条件。

例如，普通 Role A 具有统一角色编辑所需的 `role.update`，即使当前没有 `role.delete`，仍可通过编辑自身的 Application Policy 添加该权限。后续删除请求按更新后的策略重新裁决。角色编辑包含策略写入；授权也不替代 Role binding 或受保护系统 Role 的既有约束。

MatrixOne 数据委派使用与对象授权相同的五种来源，物理 WGO 不独立决定 API 准入；SELECT 转授包含目标 Role 的行列规则配置，具体合同见 [Table 与 MatrixOne](08-business-permission-model-catalog.md#54-table-与-matrixone)。

### 5.2 新增授权与撤销授权

新增授权必须校验目标资源及其 canonical 层级、scope 和授权资格。撤销授权是在目标 Role 的已保存策略中移除权限，不要求业务对象仍然存在，也不查询对象当前的层级、生命周期或删除回执。不能先解析对象，再把“对象不存在”作为特殊放行分支。

撤权仍需验证操作者的 Verified Effective Role 与策略管理权限、目标 Role 状态、策略结构和版本。完整策略替换由 Core 根据当前持久化策略计算新增与移除项；修改一条授权按移除旧项、校验新增项处理。同次提交包含无效新增项时，整次保存失败，不能先应用其中的撤权。对象删除后留下的历史授权可由管理员通过角色编辑、Application Policy 或对象授权撤销接口移除，不影响其他有效授权。

## 6. Ownership

Ownership 是应用对象的附加型 canonical 授权事实，不等于业务表中的 `created_by`。它只记录哪个 Verified Effective Role 创建并直接拥有对象，并为该 Role 增加该对象的完整普通 Application IAM 能力；它不描述对象是否存在、是否可见、是否 ready，也不能作为任何业务 action 的负向 gate：

- 创建资源时，Direct Owner 是创建动作使用的 Verified Effective Role。
- canonical active Ownership 是不可拆分的对象级完整能力：Direct Owner，或当前 Verified Effective Role 通过 active 普通 Role graph 继承到的 Owner，拥有该对象全部可授权 Application IAM 操作及其对应 grant/revoke 能力。继承边的 WGO 不参与 Owner 能力计算；Role、binding、workspace 和该 Ownership 记录本身仍必须有效。
- Owner 例外只覆盖同一 exact 对象的普通 Application IAM action，不允许转授 `grant.*` 权限本身，不替代 `role.create` 或 `role.update` 对整份 Role Application Policy 的管理，也不越过 MatrixOne DCL。
- 正常新建对象的成功条件必须同时包含业务资源和本次 Verified Effective Role 的 canonical active Ownership。同一 tenant database 使用同一个 owner transaction，Ownership、业务事实或审计任一步失败都回滚整次操作。跨库或含不可回滚外部副作用时，复用原业务 operation/Saga：在首次写入前持久化完整 intent 与冻结身份，按幂等步骤完成 Ownership 和业务激活，全部完成后才写成功终态并向调用方报告成功。失败必须返回并保留原操作的持久恢复信息；不能以日志、默认 Owner、后台补录或已提交部分业务数据代替完成。
- exact-key Ownership 缺失、non-active、畸形、重复或冲突，只表示当前没有可采用的 Owner 正向授权来源，不等同于业务资源不存在或已删除。它既不是 deny 事实，也不是授权依赖错误；Core 继续计算显式 `all`、specific、parent、path grant 和 system Role 等其它来源。最终没有任何 allow 来源时是普通未授权，不是因 Ownership 缺失而 fail closed。
- 对普通 Role，显式 `all`、specific、parent 和 path grant 只依赖 Application Policy 与 owner service 提供的 canonical 资源/层级事实，不以目标 Ownership 是否存在或 active 为 allow 条件。Owner 派生权限只在 exact-key、active 且完整的持久化 Ownership 匹配时增加 allow；不得从 workspace owner、`created_by` 或请求上下文在运行期补造 owner。
- 对当前已验证的 `admin`/`superadmin`，Application IAM 业务访问由 system Role 合同和 canonical 业务对象 lifecycle 决定；目标 Ownership 缺失或异常不得拒绝 point access，也不得让对象从 list/tree/picker 消失。历史 Ownership 补录不参与 system Role 计划或当前业务对象的授权裁决。
- 只有直接读取、transfer、repair 或 CAS 更新 Ownership 记录本身的接口，才可以因记录缺失或状态异常返回 Ownership 状态错误；该错误不能扩散为对象读写、运行、删除或 workspace readiness gate。Object Grant 的 Owner 例外需要 active Ownership，但具有 `role.create` 或 `role.update` 的管理路径不依赖目标 Ownership。业务访问在权限通过后必须执行 owner service 查询，由该查询按 workspace、逻辑删除和业务 lifecycle 决定资源是否存在；查询未命中不能返回伪造对象或成功结果。具体存储合同见[存储、生命周期与审计](04-storage-lifecycle-audit.md)，资源边界见[业务功能权限模型目录](08-business-permission-model-catalog.md)。
- IAM 引入前的历史对象如果 exact-key Ownership 完全不存在，其默认 Owner 定义为 workspace protected `superadmin`，由单次幂等补录物化。这个默认值只决定补录写入内容，不是运行期 fallback；补录失败只记录可定位的结构化日志并等待下次启动重查，不安装 gate、不改变 readiness，也不改变当前业务授权结果。
- 已有对象的 Owner Role 转移只允许当前 Verified Effective Role 被 Core 确认为该对象的 Owner，或具有当前 workspace 的 `role.update` 管理权限；Owner 匹配沿用上述 Direct Owner / inherited Owner 规则。不注册独立 transfer action，普通对象读写、创建权限不能授予转移能力。目标 Role、Ownership 版本和 lifecycle 必须校验，转移通过 canonical Ownership 写入口完成并留存审计；repair 和业务删除保留各自权限与生命周期，不能直接改 owner 字段。
- `system owner` 只描述部署或生命周期归属；`runtime actor` 只描述执行和审计身份，二者都不能绕过 Core PDP。durable execution contract 中显式冻结的 owner privilege-class 是创建时准入快照，不等同于这两个字段，也不能由它们推导。

Core 必须先按当前唯一 Verified Effective Role 独立计算每个 action 的 scope，再选择该 scope 所需的资源证明；显式 grant 使用 canonical 业务资源/层级事实，Owner 派生权限才读取 active Ownership 记录。point authorize、collection/filter、`allowed_actions` projection 和 delegation 必须复用同一 action 分类与 Effective Role Owner 匹配规则，不能各自解释 `all` 或 Ownership：

| 权限来源 | 允许范围 | 资源证明与继承语义 |
| --- | --- | --- |
| 已验证 `admin`/`superadmin` | Registry 允许 system Role 访问的全部 Application IAM action 和对象 | IAM 不预查目标；后续 owner 业务查询决定存在性与 lifecycle，不依赖目标 Ownership |
| 某 action 的 canonical `all` scope | 仅该 action 的全部同类型对象 | IAM 不预查目标；point 与 collection 都由后续 owner 业务查询决定存在性与 lifecycle，也不扩散到其它 action |
| specific/parent/path grant | 仅该 action 命中的对象范围 | owner service 证明 canonical workspace、稳定 ID、parent/path 和业务 lifecycle；不要求目标 Ownership |
| canonical active Ownership | 同一 exact 对象的全部普通 grantable Application IAM action及其 grant/revoke | Direct Owner 与 active Role graph 中的 inherited Owner 等价；继承边 WGO 不参与计算 |
| 显式 grant-action + WGO | 目标 Role 获得的 action 和 scope 的可委派能力 | 由 `role.create` 或 `role.update` 管理写入；不能由普通业务 allow 推导调用者的委派能力 |

例如某 Role 同时拥有 `compute_resource.read` 的 `all` scope、`compute_resource.update` 的 `all` scope 和某一对象的 exact `compute_resource.delete`：Ownership 状态不影响这三个显式 grant；`read.all` 不会补出 update/delete，exact delete 也不会派生任何 Owner 能力。若 delete 仅可能来自 Owner，而当前没有匹配的 active Ownership，则因没有命中 allow 而正常拒绝，不把 Ownership 缺失包装成依赖故障或额外 gate。

Registry 中的 `<resource>.owner_role_equals_effective_role` 是历史显式 condition，只表达 Owner Role ID 与 Verified Effective Role ID 直接相等；它不能代替 canonical Ownership capability，也不能据此否定 inherited Owner。Core 的 Owner capability 必须统一使用 active Ownership fact 与 lifecycle-filtered Effective Role graph 计算。

## 7. 应用权限与数据权限

Application IAM 管理 MOI 产品对象和操作；MatrixOne DCL 管理数据库、表、行列等数据面权限。二者不能相互推断：

- MOI Application IAM profile 必须在 grant 匹配和 Owner hook 之前，按 Registry 验证普通 Role requirement 中每个 action 的 `persistence_target=application_policy`；`matrixone_adapter` action 不得伪装成普通 Application Policy grant。
- `admin`/`superadmin` 是例外：它们的 protected system-role contract 在 MOI 侧直接提供全资源 allow，工作区初始化同时把完整的产品数据库/表数据面权限物化到对应 MatrixOne Role。该权限不能推广给普通 Role，也不能由一个普通 Application grant 推导。
- MOI 建立用户 SQL session 时只注入当前唯一 Effective Role 对应的 `SET ROLE`，不注入 `SET SECONDARY ROLE ALL`，也不允许 system credential fallback。
- 用户取得原生 MatrixOne session 后主动执行的 Role 切换属于 MatrixOne DCL 数据面行为；该 session Role 集合不能反向成为 Application IAM 的 Effective Role 或 allow 事实。
- 普通 Role 的 Table 查询、写入和 grant 类动作需要同时满足 Core 决策与 MatrixOne 原生权限边界；`admin`/`superadmin` 使用初始化时已物化的完整 MO Role 权限。具体合同见[业务功能权限模型目录](08-business-permission-model-catalog.md#54-table-与-matrixone)。

## 8. 集合与从属对象

- list/search/picker 必须在 total 和 pagination 之前执行 Core `ResourceAccessFilter`。
- canonical action `all` scope 或已验证 `admin`/`superadmin` 生成的 `AllResources=true` 直接执行 owner service 业务查询；该查询在同一次 SQL 中处理 workspace、逻辑删除和业务 lifecycle，IAM 不再逐对象预查或回查 metadata/Ownership。显式 specific/parent/path 产生的 `ResourceIDs` 不附加 Ownership 约束；Owner 派生的 ID 仍绑定 active Ownership proof。空 ID 集合返回空页，不能退化为查全部。
- 从属对象如果没有独立 Ownership，必须通过可信 parent resolver 继承父资源授权，不得使用 membership 代替对象授权。
- membership-only 只能用于明确登记的工作区能力或 transport，不得为缺少 canonical action 的业务对象临时兜底。

## 9. 失败语义

### 9.1 拒绝访问与系统错误分开

`fail closed` 表示没有可信授权就不执行受保护操作，不表示必须抛出系统错误、让整个页面失败或让整个 workspace 不可用。权限系统应优先把可控问题收敛为当前操作的无权限结果，并保留用户其它正常功能。

“可控”指 IAM owner 能确认影响范围，在不使用异常事实、不泄露数据且未产生本次业务副作用的前提下，给出安全的拒绝结果。异常根因尚未查明不必然属于系统故障；只要可以确定隔离范围和拒绝结果，就按可控异常处理。这个判断由唯一 PDP 或事实 owner 完成，Frontend、SDK、业务 handler 不得通过捕获任意错误自行改判。

| 情况 | 对外语义 | 影响范围 |
| --- | --- | --- |
| 未命中有效 grant；membership、Role、binding 已失效；候选角色不合法 | 无权限 | 仅依赖该身份或授权的操作 |
| 已确认缺失或无效的授权记录、悬空引用、局部权限元数据异常 | 不采用异常授权来源；没有其它独立有效来源时无权限 | 相关来源、对象或 action，不扩大为全局故障 |
| 已确认授权快照变化，既有有限重读后仍无法稳定裁决 | 本次暂不具备操作权限，保留可识别的状态变化原因 | 依赖该快照的操作，不发布旧 allow |
| Core/PDP、数据库、必要 transport 不可用，读取超时或响应合同损坏，无法取得可信结果 | 系统错误 | 依赖该故障的请求或区域 |
| 未知内部异常，无法安全确定受影响范围或操作结果 | 系统错误或既有结果未知状态 | 由 owner 明确，不能假报无权限、未写入或成功 |

“已确认缺失”必须来自成功的可信读取；数据库超时不能解释为记录不存在。局部 grant、condition 或 scope 异常时，整个受影响的 allow 来源都不可采用，不能删除限制条件后放大授权。异常影响共同身份、策略完整性或整个集合证明时，所有依赖它的结果都不可用；只有能独立证明有效的其它来源或功能才能继续。

### 9.2 返回与交互

- 未认证为 `401`；正常拒绝和可控授权异常的点查/操作为 `403`，需要隐藏对象存在性时沿用已登记的 `404`。稳定 `code` / `reason` 区分真实无授权与暂时无法使用，不把可控异常包装成 `500/503`。
- 集合仅在 Core 得到有效、完整的空可见范围时返回 `200`、空数组和 `total: 0`；能力投影可用 `allowed=false` 或从 `allowed_actions` 移除受影响动作表达拒绝。不能用空集合伪装查询失败，也不能把局部结果冒充完整列表或权限清单。
- 请求结构非法、已确认的业务冲突和可披露的资源不存在继续使用原 `400/422`、`409`、`404` 合同，不混为权限不足。真实依赖不可用使用 `503`，未知内部故障使用 `500`；已有 transport 的 `502/504` 等明确分类保持不变。
- 页面在操作、对象或局部区域显示无权限状态，避免重复错误弹窗、无限加载和全页错误。独立授权成功的内容、其它功能以及账号级导航、切换工作区、退出和适用的刷新入口保持可用。共同身份未验证时仍不能发出依赖它的受保护请求，也不能复用旧 Role 的数据或能力。
- 不可控错误也尽可能局部呈现安全、本地化提示和 request ID；只有共同依赖确实失效时才阻止相应功能集合。客户端不按错误文本猜测原因，不自动重发写请求。

本节只调整权限拒绝与故障的分类、呈现和影响范围，不改变事务完成条件。写入已开始、已部分完成或结果未知时，必须保留原业务结果与恢复合同；之后的权限拒绝不能覆盖先前操作结果。仅记录日志不能代替回滚、持久恢复或必需的 mutation audit。

### 9.3 异常诊断

可控异常也必须可排查。IAM owner 使用现有结构化 logger 记录失败阶段、稳定原因、影响范围、workspace、principal、候选/已验证 Role、resource/action、可用的版本信息及 request/trace/operation 标识，保留原始 cause；不能伪造未获得的身份或版本。具体字段命名、级别与脱敏遵循[日志与链路规则](../agent-guides/logging.md)。正常无权限走既有决策审计，不把每次预期拒绝升级为系统错误日志；可恢复异常和不可完成的故障按现有日志级别记录。

原始异常、堆栈和内部存储细节只进入受控诊断，不进入用户消息；日志也不得包含 token、密钥或未脱敏个人数据。公开响应由语义 owner 提供稳定分类与安全、本地化消息，Frontend / SDK / CLI 共同消费，见[公开错误合同](07-public-api-frontend-sdk-contracts.md#9-错误-envelope)。
