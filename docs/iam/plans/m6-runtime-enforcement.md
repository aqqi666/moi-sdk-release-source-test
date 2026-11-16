# M6 运行期权限收口计划

本文只跟踪尚未完成的运行期 PEP 工作，不重新定义授权模型。规范以[请求与运行期合同](../03-request-runtime-contracts.md)为准，当前缺口以[实现状态](../05-implementation-status.md)和[业务权限模型例外登记](../10-business-permission-model-exceptions.md)为准。

## 1. 目标

让所有异步、retry/resume/rerun、scheduled、Worker/Mowl、temporary URL 和 service-to-service 路径在实际访问受控资源前：

1. 只消费 durable context 中的 canonical actor 和 `EffectiveRoleId`；
2. 由 Core 重新验证当前 direct binding 与 lifecycle；
3. 对每个真实依赖调用 Core PDP；
4. 数据面以同一 Role 建立 MatrixOne Active Role connection；
5. Core/事实缺失时 fail closed，并保留可恢复状态。

## 2. 已闭环基线

- Backend 外部入口是唯一 Explicit Role Candidate 来源。
- Core 验证唯一 Effective Role，Worker 不做第二次 Role 选择。
- A2A Agent 准入对真实 Agent 执行一次 `agent.use` 并签发 task-scoped RuntimeGrant；Model Gateway 只验证该 grant 的冻结范围，不执行 live IAM PEP。
- 独立 Runner/Sandbox CLI 的 External Catalog 在列出 Offering 和签发 RuntimeGrant 前重验当前 workspace 成员、direct Role binding 与 lifecycle，并把 Verified Effective Role 连续传入 grant；该 transport 不定义独立模型运行时权限。
- Catalog file tools 对 canonical Volume 使用 `volume.read`。
- SQL WorkItem 使用 `ExecutionContext.EffectiveRoleId` 并在连接前重验。
- DB import 已覆盖 role context 与 MatrixOne DDL/DML 前重验。
- 显式 Runner/managed Sandbox 使用版本化 `edge_ws_authorized` transport；Astra 每次 live Edge send 前通过 Catalog gateway 重新验证 working task、Agent use、当前 Effective Role、executor 业务 lifecycle 和 `agent_runner.use` / `agent_sandbox.use`。只有本次 allow 来自 Owner 时才读取 Ownership；缺失记录不得阻断显式 grant 或 system Role。该路径禁用离线 durable relay，`eph-*` 保持服务端 conversation-bound。

修改这些基线时必须保留现有回归，不能为统一实现退回 membership/system credential。

## 3. 待收口清单

| Track | 当前缺口 | 完成标准 |
| --- | --- | --- |
| Data Task runtime | 非 DB-import worker 依赖覆盖不完整 | 每个 Connector/Volume/Database/Table/Compute 访问前按 durable Role 重验 |
| Export runtime | 源文件、Connector、外部目标链路不完整 | retry/resume 逐依赖授权，撤权立即拒绝 |
| Semantic runtime | re-embedding/source reconcile 依赖不完整 | 父 Semantic Model、source、Compute 和数据依赖分别授权并保留审计；内部模型路由不注册 `model_backend.use` |
| Direct LLM invocation | 未经 Agent RuntimeGrant 或 External Catalog 成员/Role 重验的 chat/embedding/parser 父资源与数据依赖不完整 | 解析真实产品资源后按其 action 授权；纯 transport 和内部模型路由不虚构 Model Backend 对象 action |
| Temporary URL/file delivery | 面向 MOI actor 的部分路径仍仅 membership/签名 URL | 用户/session/runtime-files 等 MOI 身份读取在实际 canonical Volume 读取前 `volume.read` + lifecycle 重验。已登记的外部模型 Catalog 文件 HTTPS capability URL 不在本缺口内，见运行期合同第 5 节。 |

## 4. 实施顺序

对每条生产入口逐一执行，不构造通用万能 grant：

1. 找到外部 admission、durable task、dispatch、worker 执行和 retry/recovery 调用点。
2. 证明 durable context 已保存 actor、Effective Role 和 canonical dependency ID；缺失时先补持久事实。
3. 在最靠近实际资源访问的 PEP 调 Core；复用公共 authorizer/client。
4. 删除该路径原有 system owner、service credential、本地 binding/cache fallback。
5. 补提交后撤权、inactive lifecycle、Core unavailable、workspace mismatch、restart/retry 回归。
6. 更新例外登记和实现状态；所有调用迁完后再把状态改为 `implemented`。

## 5. 非目标

- 不把 A2A、WorkItem Catalog 或内部 transport 产品化。
- 不新增第二个 Role Candidate、Role union 或长期离线 allow token。
- 不开放绕过 IAM capability gate 的自由创建 Role；Role 创建失败只由内部 cleanup 补偿，本计划继续跟踪其它异步资源依赖的运行期重验，不重复定义该路径。
- 不为未知未来资源设计通用 capability DSL。
- 不恢复 retired PermissionService、permission code 或本地 allow fallback。

## 6. 验收

- 当前受限 Role 即使另有 admin binding 也只能使用其 policy/scope/Ownership。
- 历史资源 target Ownership 缺失、non-active、畸形或字段不完整时，该事实既不 deny 也不形成依赖错误；匹配显式 all/specific/parent/path grant 的普通 Role 和当前已验证的 `admin`/`superadmin`，其 Application IAM 业务 point/list/tree/picker 不因此拒绝或隐藏。实际 owner 业务查询负责 workspace、存在性、层级和 lifecycle。Owner 派生权限只在 active、完整的持久化 Ownership 匹配时增加 allow；直接 Ownership mutation 仍校验记录/version，Object Grant 的 `role.manage_policy` 路径不以 Ownership 为前置条件。所有 actor 仍受 Verified Effective Role、canonical 业务 lifecycle 与 MatrixOne DCL 约束。
- Role 在提交后解绑/disabled，未执行步骤、retry 和 recovery 均拒绝。
- Core 不可用返回稳定 `503`，任务保留可诊断/可恢复状态。
- Worker payload 中的新 Role Candidate、Default Role fallback 和 system credential fallback 均被测试拒绝。
- 受控资源调用点、Core action、测试和例外登记一一对应。
