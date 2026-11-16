# 权限框架简化方案

状态：方案评审中，尚未实施。本文不改变现行规则；在方案获批并按 [rules-sync](../../../.agents/skills/rules-sync/SKILL.md) 更新 `moi/AGENTS.md` 第 12 条与 `docs/iam` 之前，[请求与运行期合同](../03-request-runtime-contracts.md)和[MOI IAM 智能体入口](../AGENTS.md)仍是唯一有效规范。

## 1. 背景

产品授权模型本身是按 workspace 隔离、带资源级授权的 RBAC：owner（`superadmin`）、`admin` 与普通 Role；普通 Role 对“资源类型 × 动作”授权，范围为全部或指定资源；资源创建者成为 Owner；用户可拥有多个 Role，请求选择一个，未选择时使用 Default Role；Role 同时映射 MatrixOne 数据权限。

现有实现在该模型之上叠加了大量框架概念，统计自 `upstream/dev` `24a88368c9`：

| 维度 | 现状 |
| --- | --- |
| 设计文档 | `docs/iam` 16 篇加 `moi/docs/authorization.md`，共 3,861 行 |
| 授权组件 | `pkg/components/authorization` 76 个生产文件，约 2.0 万行，16 个子包 |
| IAM 与身份服务 | `pkg/service/iam`、`identity` 约 1.3 万行 |
| 生成边界 | `service_boundaries.gen.go` 18,310 行，1,205 个 operation |
| 边界入口 | 12 种：`Platform`、`Authorize`、`VerifyRole`、`AuthorizeWithFacts`、`Filter`、`VerifyRoleWithFacts`、`AuthorizeWithRestoredFacts`、`Public`、`PlatformWithFacts`、`FilterWithFacts`、`FilterSelected`、`FilterWithRestoredFacts` |
| 准入类别 | 文档定义 12 种 `Admission*` |
| Service 注解 | 1,109 个 `//moi:operation`，33 种键；只有 118 种 `resource.action`、25 种资源类型 |
| 授权 facts 解析器 | 45 个 `Resolve*AuthorizationFacts`，分布在 24 个 service 文件 |
| IAM 表 | 21 张，其中约 9 张为 operation journal、锁或串行化表 |
| 身份概念 | Candidate、Verified、Effective Role、AccessClass、AccessPlan、OwnerAccessPlan、BusinessActionAuthorized、Verified Execution Identity、fact bag、fence、frozen facts |

运行成本同样集中在框架层。CI run `38549176243` 的 API 请求共 2.67 万次、36.4 万条 SQL：

| 类别 | SQL | 占比 |
| --- | --- | --- |
| 事务包装（BEGIN/COMMIT） | 85,364 | 23.5% |
| 每请求身份读取（principal、workspace member、role） | 71,230 | 19.6% |
| 审计写入 | 12,537 | 3.4% |
| 其余业务 SQL | 约 19.5 万 | 约 53% |

## 2. 目标边界：权限只在三个位置

| # | 位置 | 只负责 | 不负责 |
| --- | --- | --- | --- |
| 1 | 访问入口：API 中间件；durable task 开始执行或恢复处（Mowl case 启动、Worker 回调按 task 引用恢复）；系统任务启动处 | 解析身份 `{user, workspace, role, class}` 并放入 context；三类入口共用同一个解析器 | 不判断资源权限 |
| 2 | Service 注解 | 声明公开方法所需的检查 | 不写代码、解析器或身份参数映射 |
| 3 | 权限框架（含生成 proxy） | 按注解执行 `Check`/`Filter`；admin/owner 放行；Role policy；Ownership 登记与清理；审计 | 不做业务判断 |

durable task 在“发起”处不额外处理权限：发起本身是一次 API 请求或系统调用，已经过入口 1 和注解 2；框架只把已验证身份与 task 一起持久化。

该边界由 `moi/gates` 强制：

- `pkg/service`、`pkg/dao`、`pkg/model`、`workers` 不得 import 权限框架包；
- 不得存在 `Resolve*AuthorizationFacts` 等授权专用 service 方法，不得读取或改写 context 中的身份；
- 入口之外不得构造身份；
- 每个公开 Service 方法必须声明一种注解，缺失时生成失败。

## 3. 入口身份解析

| 入口 | 身份来源 | 建立方式 |
| --- | --- | --- |
| 用户请求（HTTP/WebSocket/SSE） | 认证后的用户，加 `X-MOI-Role-ID` 候选或 Default Role | system 读 1 次（principal、workspace、member），tenant 读 1 次（Role 与 direct binding、lifecycle） |
| durable task（工作流执行、定时、重试、恢复、Worker 回调） | 创建时持久化的 `actor + workspace + role_id` | case 开始或恢复时用同一解析器重新校验一次 |
| 系统任务（reconciler、计费、清理） | 显式 system 身份 | 只能调用声明为 `system` 的方法 |

`X-MOI-Role-ID` 只表示用户选择，从不被信任；服务端每次校验 direct binding 与 lifecycle。

durable task 权限变更语义（已确定，选项 A）：每次 case 开始或恢复时校验一次，同一次执行内复用。成员移除、Role 删除后正在执行的一次运行完成，下一次触发被拒绝。现行“owner 创建的任务冻结 owner privilege-class”的例外并入该规则。

待评审：成员移除或 Role 删除时是否主动取消该用户运行中的任务。

Worker 回调 `moi` 时只携带 Worker 自身 API Key 与 task/workitem 引用；`moi` 按引用恢复身份，拒绝 Worker 传入的用户、Role 或授权事实。该约束与现行规则一致。

## 4. Service 注解

每个公开 Service 方法只写一行，三种形态：

```go
//moi:check workflow.run workflowID   // 单对象：资源.动作 + 资源 ID 参数路径
//moi:filter workflow.read            // 列表：框架生成集合范围并注入 query 参数
//moi:system                          // 仅系统任务身份可调用
```

以及两个 Ownership 标记：

```go
//moi:creates workflow result.ID      // 成功后在同一事务登记 Owner
//moi:deletes workflow workflowID     // 删除时在同一事务清理 Owner
```

资源与动作目录（`//moi:resource`、`//moi:action`）保留为唯一定义处，只声明名称与是否可授权，其余属性使用框架默认。

现有机制的去处：

| 现有机制 | 简化后 |
| --- | --- |
| 1,109 个 operation code | 自动生成 `Service.Method`，仅用于审计与日志 |
| `principal_id=`、`effective_role_id=`（108 处） | 从 context 读取 |
| `optional_permission=`（136 处）与 `facts=` 解析器（140 处） | 删除，由被访问资源自身的 service 边界检查 |
| `boundary=platform`、`minimum_access_class=` | `//moi:system`；无注解的已认证方法默认要求 workspace 成员 |
| `restore_access=`、`schedule_identity=`、`native_workitem=` | 由入口统一解析身份 |
| `allow_if=`、`workspace_admin_if=` | 逐个审查：业务规则移回 service，授权规则进入框架 |

待评审：删除 `optional_permission` 后，工作流触发时不再预检下游资源权限，改为执行到对应节点时失败并写入执行记录。选项甲接受该变化；选项乙为必须启动前预检的场景保留由框架处理的 `//moi:precheck` 声明，service 仍不写解析器。倾向先采用甲。

## 5. 权限框架内部

- `Check(ctx, resourceType, resourceID, action)`：owner、admin 直接放行；否则查询 Role policy 与 Ownership。
- `Filter(ctx, resourceType, action)`：返回“全部”或资源 ID 集合，由生成 proxy 注入列表查询。
- Role policy 与身份事实带版本缓存：成员、Role、binding、policy 写入时递增版本使缓存失效；多实例最多做一次版本校验；缓存缺失时读库，读不到即拒绝。缓存的是事实而不是 allow，裁决仍只在框架内。
- IAM 写入与业务数据在同库时使用本地事务；只有 MatrixOne DCL（`CREATE ROLE`、`GRANT`）不可回滚，保留补偿。operation journal、串行化键、锁表随之删除。
- 身份事实目前拆在 system 库（成员）与 tenant 库（Role、binding），导致每请求至少两次往返。合并属于存储合同变更，需单独设计迁移。

## 6. Ownership

Ownership 与本方案同时设计，具体合同以调研结论补充：

- 产品语义：资源创建者的 Role 成为 Owner，Owner 对该资源拥有完整权限；
- 注册与清理只通过 `//moi:creates`、`//moi:deletes`，在业务事务内完成；
- Role 删除或成员移除后，残留 Ownership 因 lifecycle 失效而不再提供 allow，异步清理不阻塞 Role lifecycle；
- `Filter` 统一合并 Role policy 范围与 Ownership 范围；
- 数据共享撤销等跨 workspace 场景保留现有合同，迁移时单独核对。

## 7. 影响范围估计

| 层 | 内容 | 文件数 |
| --- | --- | --- |
| 入口 | 身份处理核心约 5 个 API 文件、2 个 Mowl/composition 恢复点；75 个 API 文件机械替换错误映射 | 约 10 个核心文件 |
| Service 注解 | 91 个 `//moi:operation` 文件、23 个 `//moi:action`/`//moi:resource` 文件；删除 24 个文件中的 45 个 facts 方法 | 约 100～110 个 |
| Service 签名 | 102 个文件携带 `EffectiveRoleID`/`VerifiedExecutionIdentity` 等身份参数 | 约 100 个（与上一行部分重叠） |
| 权限框架 | 76 个授权组件、31 个 IAM service、24 个 IAM DAO、4 个生成器、6 个 composition 文件 | 约 140 个，最终保留不到 30 个 |
| Schema 与升级 | 删除约 9 张 journal/锁表；只追加新 offset，不改历史 offset | 1～3 个新 offset，约 5 个表定义文件 |
| Gates | 改写 25 个权限相关 gate | 约 25 个 |
| 单元测试 | 97 个引用授权 facts 或边界的测试 | 约 100 个 |
| 集成测试 | `moi/tests` 85 个中 35 个涉及权限；权限矩阵按新模型重写断言，产品语义不变 | 约 35 个 |
| 文档与规则 | `docs/iam`、`authorization.md`、`moi/AGENTS.md` 第 12 条、`docs/iam/AGENTS.md`，收敛为 2～3 篇 | 约 20 个 |

合计约 500～650 个文件，其中生产约 300～370 个；`service_boundaries.gen.go` 由生成器重新产出。前端与 Product SDK 不修改，`X-MOI-Role-ID`、错误码与 HTTP 路由保持不变。

## 8. 实施顺序

1. 框架、生成器、入口解析器与 gates：生成器在迁移期间同时支持新旧注解。
2. 按模块迁移注解与 service，每个模块一个 commit 并运行该模块的单点集成测试；顺序为智能体、知识库、工作流，然后其余模块。
3. 全部迁移后删除旧框架、旧表与旧文档。新旧并存只存在于迁移期间，不保留长期兼容层。

## 9. 验收

- gates 证明第 2 节的三层边界；
- 每请求身份读取不超过 system 1 条、tenant 1 条（缓存命中时为 0）；
- 现有权限矩阵集成测试的产品断言全部通过，拒绝时零 mutation；
- durable task 按第 3 节语义在 case 开始与恢复时重新校验，Worker 传入的授权字段被拒绝。
