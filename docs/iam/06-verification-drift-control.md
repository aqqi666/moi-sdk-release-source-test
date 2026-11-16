# MOI IAM 验证与漂移控制

本文定义修改权限实现或文档时的最小证据。命令从指定工作目录运行，不能通过跳过测试、放宽断言或恢复 legacy 空壳绕过。

## 1. 权威与派生资料

- Core Registry/operation definitions：`moi-core/catalog/pkg/iamcore/canonical_registry.go`。
- Core PDP：`moi-core/catalog/pkg/iamcore/authorizer.go`、`authorize_boundary.go`、`resource_access_filter.go`。
- Backend transport/PEP：`moi-backend/pkg/iampep`、`moi-backend/pkg/coreclient`。
- Core transport guard：`moi-core/catalog/pkg/api/backendauth`。
- Shared engine：`shared/authz`。
- [业务功能权限模型目录](08-business-permission-model-catalog.md)：业务功能/API 到 action、授权层级、Ownership 和依赖资源的规范性查阅合同。
- [Registry 快照](09-business-permission-model-registry.md)、实现状态、route matrix：派生资料，不参与运行期 allow。
- [业务权限模型例外登记](10-business-permission-model-exceptions.md)：未进入 canonical 产品资源模型的当前边界，不产生新的 allow 规则。

当派生资料与代码不一致时，先判断是实现缺陷还是文档漂移；资源/action 产品语义变化仍需用户确认，不能只更新代码或只更新文档。

## 2. Registry 与 route gate

从仓库根目录运行：

```bash
cd moi-core/catalog
go test ./pkg/iamcore -run 'TestCanonicalIAMRegistry|TestIAMRouteActionCoverageChecker' -count=1
go run ./cmd/iam-route-action-checker
```

checker 当前验证 canonical action/resource、Backend route binding 和已登记的 Backend/Core 合同样本。它不是全量静态证明；新增生产 route 时必须把对应合同纳入 checker 或 architecture test，不能因为 checker 未覆盖就视为安全。

checker 同时精确比较 `docs/iam/09-business-permission-model-registry.md` 标记区间中的 Registry schema、resource 和 action。operation requirement 不复制到 Markdown，仍由 Registry 测试和 route/action 合同检查证明。

文件请求准备的定向合同测试包括 Backend `TestCatalogVolumePEP*`、Core `TestRequestAuthorization*`、`TestCatalogVolumePreparation*`、`TestCatalogRequestPlan*` 和两端 `TestCatalogAuthorization*`。它们分别证明 1/100/1000 个文件只发一次准备调用、Root 去重后批量裁决、后续门禁精确复用、管理员权限准备零读取，以及失败时业务不继续、错误分类和双语提示稳定、原始原因只进入受控日志。准备响应缺少计划、签名损坏或状态不符合合同均不得进入业务 handler。

未挂载文件的回归必须覆盖：无 `volume.*` 权限的普通有效成员访问同 workspace 中真实存在的未挂载文件成功；非成员、跨 workspace、文件不存在、挂载关系异常及必要事实不可用均拒绝；文件挂载后切换到 canonical Root/action 授权，不能复用先前的成员准入。不能仅把管理员旧用例的 404 改为 200；还须证明普通成员路径符合合同，并保留 Admin/SuperAdmin 权限准备零读取的断言。

## 3. 授权内核

```bash
cd shared/authz
go test ./... -count=1

cd ../../moi-core/catalog
go test ./pkg/iamcore -count=1
```

至少覆盖：

- Explicit Role 不读取或回退 Default Role；
- current restricted Role 不因另有 admin/superadmin binding 获得 allow；
- inactive user/member/Role/binding/workspace fail closed；
- `admin` 和已验证 owner `superadmin` 走 protected system-role fast path；工作区初始化必须已为对应 MatrixOne Role 物化完整产品数据面权限，普通 Role 才走逐对象 DCL 事实校验；
- `admin`/`superadmin` 的 point/list/tree/picker 及 canonical action `all` collection 不因 target Ownership 缺失、non-active、畸形或字段不完整而拒绝/隐藏，也不在 IAM 中预查目标 metadata；owner 业务查询未命中时返回 `404`/空结果，查询不可用时 fail closed；
- point Authorize 与 filter 使用同一 facts；
- unknown action、malformed facts、storage/Core unavailable fail closed；
- 普通 action（包括 create、MatrixOne DCL action 和 grant/WGO action）沿 Role graph 继承；同步覆盖继承边、Role、binding 和 workspace lifecycle 失效；
- active Direct Owner 和通过普通 active Role graph 继承到的 Owner，都能授予/撤销同一 exact 对象的普通 grantable Application IAM action；继承边 WGO 为 false 时 Owner 能力仍完整；
- 非 Owner 的普通业务 allow 不能替代授权证明；Object Grant 和 MatrixOne Data Privilege 委派由同一 Verified Effective Role 的 workspace `role.create` 或 `role.update` 管理，且该管理路径不得预读或要求目标 Ownership。没有该大权限时，只有当前 exact Owner 才能按 WGO 语义委派自己的对象；Ownership 缺失只让 Owner 例外不命中并返回普通未授权。目标 action、scope、grant option 和 MatrixOne DCL 仍由 Core/适配器校验；Owner 不能越过 MatrixOne DCL；
- Role graph 读取完整单快照，深度超过 32、节点超过 4096、边超过 16384 时仍使用完整事实；缺失、损坏与已有 cycle 保持现有 Core fail closed 语义；
- 继承修改的历史 pending 不阻塞新写与删除；相同请求不重放，历史成功在撤边后仍只返回历史结果；
- 不相交角色对可并行，同角色修改/禁用/删除与继承写共享行锁；pending 未写成功不执行 MO，MO 明确成功后日志失败仍返回成功；
- 继承修改的超时/断连保留 pending，进程重启不执行历史请求；MO 明确拒绝的错误经过 owner 本地化后由前端和 SDK 原样展示；
- policy generation before/after fence、Grant Index 同事务更新和连续变化拒绝；
- 对象删除后，通过角色编辑、Application Policy 和 Object Grant 撤销历史授权，保持未移除项、Policy 与 Grant Index 一致；撤权不依赖业务资源查询，仍拒绝无管理权限或版本过期的请求。混合提交支持同时移除已删除对象与现存对象的授权；新增或改授不存在对象时整次失败，原策略不变；验证请求不写入，成功请求重放不重复修改；
- 除继承结果日志外，需原子提交的 durable mutation audit 失败仍回滚；decision recorder 失败不改变裁决；
- 只存在 request-scoped fact reuse，不引入跨请求 decision cache；
- owner access plan 必须在业务 SQL 前生成并绑定 Verified Effective Role、policy、Role Graph 与 binding/lifecycle；canonical action `all` 和 system all-access 直接使用后续 owner SQL 结果，显式 exact specific scope 不绑定 Ownership snapshot，Owner 派生 ID 才绑定完整 active Ownership snapshot；parent/path collection 使用通用 `ResourceAccessFilter`，不伪装成 bounded plan；
- Compute 的 canonical `read.all` 或 system all-access 必须生成 `all`；显式 exact specific 与 Owner 派生 scope 只能物化为 `specific` 或 `empty`。restricted ID 必须下推 storage，`empty` 不得查询 owner storage，显式 scope 不得读取 target Ownership；
- `uniform_allow` 只能来自对应 action 的 canonical all scope，candidate projection 只能读取 SQL 实际结果；不能用 handler 本地过滤代替 pre-SQL plan，也不能把 read action 的 `all` 扩散到 update/delete/operate；
- canonical `read.all` 结果中的 candidate action 最多处理 100 个实际结果：没有 active Ownership 的对象仍可获得匹配的显式 exact action，只是 Owner 派生 candidate 为空；该 action 自身的 canonical `all` 仍可独立 `uniform_allow`；parent/path candidate 在 owner 查询未返回 canonical 层级时不得伪造匹配；
- candidate Ownership 子集必须证明普通缺失/non-active 对象被当作“不提供 Owner allow”而不是请求错误；对已经采用的 Owner 记录，再覆盖 extra/duplicate/key mismatch/invalid version/storage error 和前后漂移，最终 fence 必须比较完整 record，不能只比较 ID 或 status；
- Owner 派生 proof 的 strict exact-ID batch 必须证明 0/dirty/duplicate/>100 输入不发 SQL，1/100 成功，missing/extra/duplicate/key mismatch/non-active/invalid version/repair state/storage error 无 partial result，并按请求顺序重建；显式 ID 不进入该 batch，reader 缺失时不得为 Owner 分支做 point fallback；
- Owner 派生 proof 的 T1 active inventory、T2 batch read、T3 batch readback、T4 complete-result final read/readback 必须覆盖 owner status/version/Role 漂移；显式 scope 的对应计数必须保持 0 次 Ownership read，批量 projection 的 discovery 次数保持常数；
- canonical policy-all 与 system-all 必须覆盖 target Ownership missing/non-active/incomplete 时权限计算仍成功且 target Ownership 读取为 0；owner 业务查询未命中返回 `404`/空结果，逻辑删除或 lifecycle 非法对象不得被查询返回；
- 同一 action 的 canonical policy-all 必须同时覆盖 collection plan 与 point Authorize；两者都不得读取 target Ownership，且其它 action 不得继承该 all 结论；
- 每批上限、opaque proof、完整结果集 final fence，以及零行/not-found 时的 policy、Role Graph、binding/lifecycle freshness fence 均 fail closed；
- `allowed_actions` 只用于展示，不能替代 mutation 的 point Authorize。

### 3.1 IAM 读取、写入与连接优化回归

性能优化同时验证调用次数和原有失败语义。计数必须限定到对应阶段；批量 SQL 的参数量和结果量仍随输入增长，固定往返次数不等于固定总成本，也不能替代真实环境耗时测量。

- 成员展示：用 1/100 个成员证明完整事实固定 5 次 tenant 查询、只读 profile 固定 1 次；空集合和非法输入不执行批量 SQL。证明身份授权先于 tenant 读取、成员顺序与 disabled 展示不变、可选事实缺失保留原值，以及任一查询/迭代错误整体失败。入口：[service 回归](../../moi-core/catalog/pkg/iamcore/workspace_members_batch_test.go)、[storage 回归](../../moi-core/catalog/pkg/service/storage/tenant/iam_workspace_member_reads_test.go)。
- 对象权限来源 Role：用 1/100 个来源角色证明一次 canonical 单语句快照读取，第二次调用读取新 lifecycle/图版本。覆盖空输入、缺失或额外 Role、重复结果、workspace/key 不匹配、deleted/未知 lifecycle、非 ready provisioning、无效版本、数据库错误与图依赖失败，不得返回部分结果。管理视图保留 disabled owner 与 direct/all-scope 来源及其状态；用真实 Product SDK 与同一普通客户端证明停用后实际读写仍拒绝、授权 validate/apply 不写入、重新启用后恢复。入口：[view 回归](../../moi/pkg/service/iam/object_permission_test.go)、[storage 回归](../../moi/pkg/dao/tenant/iam_object_permission_test.go)、[Connector Product SDK 回归](../../moi/tests/permission_connector_legacy_matrix_test.go)。
- 标签替换：证明非空有效批次只有 DELETE、定义批量加锁与多行 INSERT 三条替换 SQL；空输入清空、已删除定义跳过、非法值与重复有效键失败回滚，并覆盖 profile/标签/mutation audit 的原子性。入口：[storage 回归](../../moi-core/catalog/pkg/service/storage/tenant/iam_subject_attributes_test.go)；[MatrixOne live 回归](../../moi-core/catalog/pkg/service/storage/tenant/iam_subject_attributes_matrixone_integration_test.go)补充真实 SQL、锁与回滚验证，不由 mock 计数代替。
- 用户 SQL 连接：证明 handle 创建与缓存健康检查零物理建连，每次实际获取会话才初始化 Role/标签，归还后零空闲连接；建连、Role/标签初始化和超时失败时不执行业务 SQL、不自动重放，并保留错误码、双语提示和内部 cause。下一次池获取应重读凭据并关闭旧 handle；管理连接探活仍失败即拒绝。入口：[用户连接回归](../../moi-core/catalog/pkg/service/storage/tenant/connection_pool_user_probe_test.go)。
- Schema 缓存：证明 Core service 只构建一次、返回的嵌套集合独立、重建 service 后指纹随事实变化；Frontend 的并发合并、TTL、回收、跨 QueryClient 隔离、命中缓存时 observer 校验、预览不污染共享数据、切换 workspace 的保留范围均须覆盖。创建/编辑版本冲突要证明强制读取、保留草稿、刷新失败阻止旧版本提交，以及下一次显式保存按接口合同创建新操作；角色编辑可以省略业务 request ID。入口：[Schema provider 回归](../../moi/pkg/components/authorization/permission_schema_test.go)、[前端完整测试矩阵](../../moi-frontend/modules/moi-permission/src/permission-schema-query.test.md)、[产品 API Schema 合同回归](../../moi/tests/menu_workspace_roles_test.go)。

对应实现为 [#18133](https://github.com/matrixorigin/matrixflow/pull/18133)、[#18140](https://github.com/matrixorigin/matrixflow/pull/18140)、[#18123](https://github.com/matrixorigin/matrixflow/pull/18123)、[#18105](https://github.com/matrixorigin/matrixflow/pull/18105) 和 [#18101](https://github.com/matrixorigin/matrixflow/pull/18101)。纯文档更新只做链接、契约引用与差异检查；实现变更按受影响路径运行必要的定向回归，真实 MatrixOne 和跨服务回归由 CI 承担。

### 3.2 事务与重试合同验证

实现[事务标准](04-storage-lifecycle-audit.md#41-事务与持久恢复边界)和[保存交互标准](07-public-api-frontend-sdk-contracts.md#11-保存与重试的统一原则)时，按本次真实边界选择以下定向场景，不为不存在的状态新增流程：

- 同事务写入：业务、Ownership／投影、版本或必需审计失败时均无部分提交；成功提交但响应丢失不能误判为已回滚。
- 整角色 PATCH：本次无 MO 变化时，即使 DCL 不可用仍可完成本地保存；跨 MO 时最终审计写入失败必须回滚全部 MOI 业务事实，保留已完成的 MO 授权，确认持久失败终态后释放原请求占用。新保存可更改输入或撤销旧部分授权，未涉及的旧部分结果由 owner 管理员处理；共享恢复可依据成功回执完成 Saga 记账，不重写业务事实。
- 普通保存：支持的接口不传业务 `request_id` 也能完成；新版本上的重复设置按新保存处理，旧版本仍冲突。不得用固定 SQL 数量、源码文本或函数形状替代最终数据和错误语义断言。
- 跨事务中断：分别覆盖只有 intent、MO 部分完成／结果未知、MO 已完成而 MOI 未确认，以及业务已完成但 Saga 终态未保存；核验后只执行该阶段允许的动作，不重复旧 DCL。
- 服务端生成请求编号：客户端未收到编号后，共享调度器独立完成过期原编辑，普通新保存和原请求确认均不接管；验证活跃租约仍互斥、原收尾推进版本后仍返回正常 CAS 冲突、刷新后的新保存成功，以及原请求重试不改动新设置。prepare、MO 和 commit 的确定性错误重试保持原分类。
- 历史独立权限：旧格式 `applying` 回执无 Saga 时，覆盖显式 repair 和新保存仅释放历史占用、不导入旧投影；验证完整 intent/hash、后续版本 CAS 和旧 GRANT 不覆盖新 REVOKE，新格式缺少 Saga 仍拒绝。
- 重试与并发：新保存先取得运行租约再暴露可恢复意图，共享调度器不能抢占首次执行；原请求确认和进程重启不重开预算，耗尽的终态不再被扫描；A 仍在执行或终态未确认时 B 被拒绝。整角色编辑 A 确认停止后 B 可正常提交，过期恢复 claim 和旧请求 A 均不能再覆盖 B；覆盖释放失败后的新保存，以及两次保存之间出现另一失败操作的版本冲突。其它 Role 的正常保存不受影响。
- 人工修复：重新鉴权、稳定对象身份与版本校验有效；以 MO 最新事实更新 MOI，修复失败不解除隔离，成功回执、投影、版本、审计与解除隔离共同提交。查询和 GET 不产生修复副作用。
- 真实调用方：保存中防连点；整角色编辑失败保留草稿和保存入口，刷新必要事实后可修改并重新提交。刷新冲突版本后由用户再次确认，下一次普通保存携带当前草稿而非缓存旧 payload。SDK 保留稳定错误、版本和诊断信息，不自动重发写入。

数据库原子性、DCL 副作用和跨事务故障由真实集成场景证明，组件测试只证明浏览器交互；接口编译或 mock 成功不能据此宣布可转测。纯文档更新只检查链接、合同一致性和差异，不启动环境或运行全量测试。

### 3.3 拒绝分类与故障隔离验证

实现[失败语义](01-product-authorization-model.md#9-失败语义)时，按受影响 owner 选择定向回归，不能仅断言“请求被拒绝”或“返回非 2xx”：

| 场景 | 必须证明 |
| --- | --- |
| 可控授权异常 | 已确认缺失、停用、局部坏事实与有限重读后的版本变化返回稳定无权限分类；没有本次受保护读写副作用，并保留异常原因与影响范围 |
| 独立授权来源 | 无效 Owner/grant 不参与 allow；另一个完整有效来源仍可授权，不能通过丢弃 condition/scope 放大范围 |
| 读与动作投影 | 同一对象 read 仍有效、某个写动作投影异常时，返回可读内容及其余有效动作；异常动作不可用，实际写入仍由服务端独立鉴权 |
| 共同事实失效 | 身份、read scope 或完整结果证明失效时不返回依赖它的数据，不把局部结果当成完整列表；可信空范围仍返回空页，查询故障不能伪装为空页 |
| 页面隔离 | 局部无权限不造成整页错误或无限加载；共同 Role context 失效后不残留旧能力，但账号导航、切换工作区和退出仍可用；旧请求不能覆盖新上下文 |
| 不可控故障 | Core/storage/transport 不可用、超时、损坏响应和未知内部异常保留真实错误分类、安全消息与 request ID，不能泛化为 `403` |
| 已开始的写入 | 部分生效、结果未知、回滚失败和必需 mutation audit 失败保留既有业务结果及恢复合同，不能由后续拒绝覆盖或仅写日志后报成功 |
| 可诊断性 | 可控与不可控异常都能按 request/trace 关联 owner、阶段、资源/action、影响范围和原始 cause；响应与日志均不泄露凭据，正常拒绝不形成系统错误日志噪声 |

同一次异常注入应同时验证受影响功能拒绝与无关功能仍成功。纯设计更新只检查合同一致性、链接和差异，不代表上述行为已实现；实现时本地只运行必要定向测试，完整矩阵交由 CI。

## 4. Backend/Core 合同

```bash
cd moi-backend
go test ./pkg/iampep ./pkg/coreclient -count=1
```

对象、集合、Object Grant 和 membership-only 四类合同必须分别证明：

- `Require` 对应 Core `WithCurrentCoreAuthorization`；
- `PrepareCoreRequestContext` 对应 Core-owned `Authorize`/`ResourceAccessFilter` 或 Object Grant Owner-or-delegation mutation，不能要求 Backend 预授权；
- `RequireVerifiedEffectiveRole` 对应 Core verified-role guard，不伪造业务 allow；
- 仅 `authzpolicy passThrough` 的 route 不能调用要求 current business authorization 的 Core route；
- Core 403/503 保留真实非 2xx 和错误分类。

涉及 Role Candidate 解析、workspace membership middleware、Current Principal projection 或请求级裁决复用时，还必须用生产 route 的真实 middleware 顺序覆盖以下状态转换：

1. 显式 candidate 在 Core verifier 调用处可见，`VerifiedEffectiveRoleID` 仍为空；
2. Core 返回唯一 Effective Role 后，handler 看到 `RoleCandidateID` 已清空且 `VerifiedEffectiveRoleID` 已写入；
3. `/newmoi/user/info` projection 与当前 account、workspace、request、trace 一致，且 projection 返回的 Effective Role 与请求上下文中的 `VerifiedEffectiveRoleID` 一致时成功，不能再与已清空的 candidate 比较；
4. candidate 未消费、verified role 缺失或变化、projection 绑定变化时均 fail closed；
5. 无显式 candidate 的 Default Role 路径仍由 Core 选择并产生 verified fact，不能由 Backend fallback。

这类回归不能只直接调用 verifier，也不能手工构造校验后的 context；否则会绕过“candidate 被消费并替换为 verified fact”的真实阶段，无法发现 middleware 顺序和 projection 复用错误。Product SDK 或 CLI 新增 Role transport 能力时，还必须用真实 PAT 和 Backend route 验证 `/newmoi/user/info` bootstrap；只断言出站 header 或 Core 单点响应不足以证明端到端合同成立。

顶层 BFF 数据树请求计划还须用定向契约测试证明：

- 同 Root、同 action 的 1/100/1000 个文件，Role 验证与完整批量 PDP 均为 1；多个 Root 去重后一次批量补充；
- 真实 SDK transport 的同一请求跨接口、单个 Execute 中多次 HTTP、并发子调用共享最新结果；请求关闭后即使 `WithoutCancel` 也不能发送；
- 新 Root/action 只补充未覆盖范围；point 与 collection 分离，普通 BFF allow 和 UI projection 不能产生数据树 allow；
- 新请求及 principal/workspace/Role 不匹配、签名篡改、重复 header、非可信 transport 均拒绝复用；
- 首次门禁 Core/PDP 不可用 fail closed；计划已覆盖时移除全部 PDP 依赖仍可精确匹配；
- Admin/SuperAdmin 从可信 Verified Role 直接取得全量范围，权限准备和目标元数据读取均为 0；错误测试断言双语提示、稳定 reason/domain、内部原因只出现在日志。

### 4.1 统一准入与身份状态门禁

[请求身份与统一准入](12-request-principal-admission.md)已建立下列本地门禁与定向回归。实际覆盖为 816 个 workspace 入口、canonical 288/288；CI 跨服务/版本组合及 QA 复测未执行。证据入口和限制见[实施计划](plans/request-principal-admission.md)。

- 扩展现有 architecture test，以 Go AST/类型信息检查 Candidate 只在入口解析和首次 Core 调用处使用；业务包不能调用候选 accessor、直接写身份字段或构造 Verified 类型。文本搜索只用于盘点，不能替代门禁。
- IAM transport 的 acting Role 由公共 adapter 从身份构造；覆盖 protobuf body、执行 header、响应固定 Role 和 actor/target Role 分离。禁止以反射统一填充所有同名 `role_id`。
- 扩展现有 route/action checker，验证每条 workspace route 的准入类别、真实 middleware 顺序、首次准入前 tenant 读取和 handler 所需 plan；新增路由不能靠未声明类别获得 membership-only 行为。
- 覆盖集由实际注册路由与 IAM route/Registry 合同双向对账生成，包含独立 route group、IAM 管理和 bootstrap；不能只检查已知缺陷调用点。每条应接入路由必须使用公共准入组件，结果类别差异不能成为手工拼装身份或另建流程的理由。全量迁移验收记录总数、已迁移数和未迁移项，未迁移项必须为零；排除项只能引用已有边界/例外登记。
- 生产 middleware 顺序的真实链路用例必须包含“默认 admin + 显式 restricted”、无显式候选、请求中途 Default Role 改变、多个后续 action、body/header 冲突、缺失身份/新协议字段，以及同 request ID 的独立请求。不能只测试 accessor 或只断言 header。
- 准入失败或计划缺失时，通过业务 storage/副作用 spy 证明没有受保护 I/O；合法 empty scope 仍为 200 空页，filter 在 count/page 之前生效。
- 对同一 Core attempt 增加 fact reader 的调用计数与并发/取消测试；未完成裁决所需 final fence 独立计数，snapshot retry 重建事实而不重选 Role。活跃请求计划保留已验证角色与已完成精确范围，没有该计划的独立 Core 调用继续验证当前角色事实。
- 用统一准入与真实 Core 请求计划共同执行 Verify、合并 Authorize/filter，验证角色 Source/Version 不变、下一请求感知撤权；首次数据树 filter 必须发布可复用的集合范围，Owner 精确 ID 不要求业务 SQL 再次查询 Ownership，集合范围不能授予 point 或新 action。计划命中与首次/未覆盖范围的 PDP 次数分别计数。
- connector 合并准入的 RPC 计数固定为一次 filter、零次完整角色展示投影；parent resolver 类按其真实二阶段合同验证。不同资源动作不能为满足一次 RPC 指标而省略裁决。

协议生成、角色语义、新旧版本发布和边界验证由 CI 的定向/跨服务用例承担。普通本地执行仍遵守最小充分范围；文档改动只运行轻量检查，不因此启动应用或全量回归。

## 5. 资源测试矩阵

每个新增或修改的资源至少覆盖：

| 场景 | 必须证明 |
| --- | --- |
| admin/superadmin | 当前 Verified Effective Role 有效时，对 MOI Application IAM 直接成功；对应 MatrixOne Role 的完整产品数据面权限由 workspace bootstrap/readback 证明 |
| target Ownership 状态 | 缺失/non-active/畸形 Ownership 既不 deny 也不返回依赖错误；匹配的显式 all/specific/parent/path grant 和 `admin`/`superadmin` 的 point/list/tree/picker 行为不变；Owner allow 只在 active、完整记录匹配时增加 |
| Owner delegation | active Direct Owner 和通过非 WGO 普通 Role 边继承到的 Owner，都可授予/撤销同一 exact 对象的普通 grantable action；disabled Role/Ownership 拒绝 |
| non-owner delegation | 普通 action allow 不足；同一 Verified Effective Role 必须具备 workspace `role.create` 或 `role.update`，目标 action/scope/WGO 由 Core 结构校验；该路径在 target Ownership 缺失时仍成功且不读取 Ownership |
| business create/delete | 同库业务与 Ownership 任一步失败均整体回滚；跨库故障不得报告成功或写 completed，必须保留原 durable intent 并在重启后完成；确认缺失可幂等跳过，读取/写入/CAS 错误不能伪装为缺失 |
| Role lifecycle/delete | active Ownership count 仅用于展示和清理观测，不阻断普通 Role disable/delete；Role 失效后残留 Ownership 不提供 allow，清理失败只写完整日志 |
| restricted Role | 只按当前 policy/scope 裁决；Owner 分支才读取 Ownership，其它绑定不参与 |
| lifecycle | inactive binding/Role/user/workspace 拒绝 |
| transport | Core unavailable 返回 503，无本地 fallback |
| isolation | workspace/Role/resource parent 不一致拒绝 |
| collection | 过滤先于 count/pagination，空 ID 不查全部 |
| async | durable actor/Role 固化；普通主体实际访问时重新授权，owner privilege-class 仅从完整的创建时 task/job 快照恢复 |
| recovery | restart/readback 收敛；永久错误 fail closed |

历史 canonical 对象 Ownership 补录还必须证明：owner service 精确解析 workspace、资源类型、稳定 ID 与业务 lifecycle；candidate query 只返回 exact-key Ownership 完全不存在的对象，已有 active、non-active、tombstone、重复、畸形或冲突事实均不覆盖。补录只以默认 `superadmin` Role 通过 canonical writer 单次幂等写入缺失 Ownership，不创建补录专用 lifecycle 状态机；正常新建对象必须登记实际创建 Role，不走历史默认值；登记失败按统一创建一致性合同回滚或保留原未完成操作，不能报告创建成功。Catalog 与 Root Volume 的验证必须覆盖：缺失记录成功补录、任意已有 exact-key 记录保持不变、并发创建/删除安全收敛、第二次启动幂等；candidate inventory、workspace facts、transaction、writer/readback 或 rollback 失败后，日志包含 `component`、`operation`、资源类型、可用的 `workspace_id`、`failure_scope`、`failure_kind`、`retry_policy`、部分进度和原始错误，后续 workspace 与 `Server.Start` 均继续，失败 workspace 在本进程中不重试并由下次启动重查。测试还必须证明补录只是元数据补全：无论是否成功，都不改变授权结果、业务 API、Object Grant 的管理路径或 readiness；没有 Ownership 时 Owner 来源不命中，其它来源照常裁决。

API Service 还必须证明：伪造 `api_service_id` 或仅携带通用 Backend authorization 的部署在进入 saga/ownership 前拒绝；publish 的 source/compute dependency 都是精确 canonical facts；同一 WorkItem version 重发布复用稳定 WorkflowApp ID；运行期重新裁决 `api_service.run` 和 `compute_resource.use` 且 Effective Role 一致；worker-backed 服务未 ready 返回 `FailedPrecondition`、ready 后才调用 Mowl。

跨数据库、MatrixOne DCL 或真实 transaction 边界不能只靠 mock；需要对应 integration/latest-upgrade gate。

公开 Backend/Product SDK IAM 合同还要覆盖 [公开 API、前端与 SDK 合同](07-public-api-frontend-sdk-contracts.md) 中的字段语义、CAS、validate-only、错误 envelope 和路由映射。生成类型只能由 proto/生成器更新，不能手改生成文件。

## 6. Upgrade gate

涉及 schema、offset 或 hard removal 时先读 `moi-core/catalog/pkg/upgrade/AGENTS.md`，再从仓库根运行：

```bash
bash .github/scripts/check_upgrade_offset_guard.sh "$(git merge-base upstream/dev HEAD)"
bash .github/scripts/check_schema_upgrade_guard.sh "$(git merge-base upstream/dev HEAD)"
bash .github/scripts/run_auto_upgrade_latest_gate.sh "$(git merge-base upstream/dev HEAD)"
```

同时运行当前 offset handler 和 latest fixture 的聚焦 Go 测试。不得在通用 gate 脚本中硬编码 offset 或产品 seed。

## 7. Canonical IAM boundary 与 Frontend E2E

从仓库根目录运行 canonical IAM boundary checks：

```bash
python3 scripts/ci/iam_canonical_boundary_check_test.py
python3 scripts/ci/iam_canonical_boundary_check.py
python3 scripts/ci/iam_frontend_canonical_boundary_check_test.py
python3 scripts/ci/iam_frontend_canonical_boundary_check.py
```

涉及 Frontend Role、权限 schema、Data Privilege 或错误展示时运行 `moi-frontend/apps/moi-app/e2e/iam/iam-role-management.spec.ts` 对应套件。mock E2E 只证明浏览器交互、route 和错误映射；只有接入真实 Backend/Core/MatrixOne 的测试才能证明 PDP、DCL、readback 与 SQL allow/deny。未运行真实环境验证时必须明确记录。

历史策略编辑回归由 `iam-role-permission-feedback.spec.ts` 分别验证两类状态：当前 Schema 中不存在的历史 action 显示退役提示，打开和取消不写入，显式保存只发出一次统一角色 PATCH，清理退役项并保留有效授权、资源范围与 CAS；当前 Schema 仍定义的 action 携带合法但编辑器无法安全回写的 condition 时，显示不支持配置的提示并禁用保存。两类 fixture 不得混用。仅修改元数据或权限后的清理、Schema 冲突与草稿保留由对应组件测试覆盖；提交失败还须由 owner 测试证明未提交的历史 Policy 保持原值、失败终态释放占用且新编辑仍可保存，不能用 mock E2E 代替。

系统 Role 预览的规范见[公开合同第 3.3 节](07-public-api-frontend-sdk-contracts.md#33-role-权限预览)。回归入口为 [IAMRolePermissionPreviewModal.test.tsx](../../moi-frontend/modules/moi-permission/src/pages/role-list/components/IAMRolePermissionPreviewModal.test.tsx) 和 [permission-preview.test.ts](../../moi-frontend/modules/moi-permission/src/pages/role-list/permission-preview.test.ts)，业务验收点见[配套测试说明](../../moi-frontend/modules/moi-permission/src/pages/role-list/components/IAMRolePermissionPreviewModal.test.md)。这些定向测试必须同时断言展示结果和请求次数，至少覆盖：

- `admin`、`superadmin` 都从 Schema 展示应用与数据库/表权限且 scope 全为 `all`；Schema 新增 action 自动出现，不受普通角色可配置 scope 或数据权限编辑能力限制。
- 首次打开、Schema 缓存命中和错误后重试均不调用 Role Permission View 或 Data Privilege；旧明细缓存错误、损坏或 pending 不阻塞系统 Role 预览。
- Schema 加载、合法空清单、读取错误、损坏响应与权限拒绝分别进入对应状态，不能因系统 Role 身份绕过 Schema 合同校验。
- 仅名称相同、其他受保护角色或缺少稳定系统角色标识的目标仍读取实际权限；系统 Role 与普通 Role 在同一弹窗中切换时，加载状态、scope 和查询路径随目标切换，不能残留 `all` 或明细错误。
- 系统 Role 不提供编辑、资源列表或行列详情入口；该展示测试不宣称验证了服务器授权或真实 MatrixOne enforcement。

CI 在现有 `frontend-main` 的 `RUN_FE_MOI_APP` 分支中执行这两个测试文件，失败会使该 lane 失败；不依赖 `moi-app` 单测扫描模块目录。只修改该预览时，可从 `moi-frontend/modules/moi-permission/` 运行最小回归：

```bash
pnpm exec vitest run src/pages/role-list/components/IAMRolePermissionPreviewModal.test.tsx src/pages/role-list/permission-preview.test.ts --maxWorkers=1
```

Data Privilege 的 database/table DCL 和 literal row/column capability 必须分别测试。行列能力只有 live probe 成功且 `row_column_contract_ready`、`row_column_rule_schema_included`、`row_column_enforcement_verified` 同时为 true 时才能启用；测试不得用 MatrixOne 版本字符串或 mock capability 代替真实 enforcement 证明。

## 8. 文档防漂移

修改权限代码时检查：

```bash
rg -n "IAMResource|IAMAction" moi-core/catalog/pkg/iamcore/canonical_registry.go
rg -n "WithCurrentCoreAuthorization|WithCurrentVerifiedEffectiveRole" moi-core/catalog/pkg/api/router.go
rg -n "iampep.Require|PrepareCoreRequestContext|RequireVerifiedEffectiveRole" moi-backend/pkg/handlers moi-backend/cmd
```

随后：

- Registry schema、resource 或 action 变化时更新 [Registry 快照](09-business-permission-model-registry.md)，并通过 checker 的精确集合比较；
- 业务功能/API、route action、授权层级、parent resolver、Ownership 或运行期依赖变化时更新 [业务功能权限模型目录](08-business-permission-model-catalog.md)；
- 更新 [实现状态](05-implementation-status.md) 的证据和状态枚举；
- 新增/关闭 membership-only、transport-only 或 runtime gap 时更新[业务权限模型例外登记](10-business-permission-model-exceptions.md)和 [M6 计划](plans/m6-runtime-enforcement.md)；关闭 legacy 资产、兼容入口或发布验收项时更新 [M8 计划](plans/m8-legacy-hard-removal.md)；
- 检查所有 Markdown 相对链接和 `git diff --check`。

禁止手工从文档向代码复制一套 action dictionary。资源索引只帮助查阅，最终一致性由 Registry tests、route checker 和 owner-module tests 证明。
