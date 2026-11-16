# MOI IAM 智能体入口

本目录是 MOI 新权限系统的维护入口，适用于权限接入、权限修改、权限缺陷修复、权限评审和 legacy 权限清理。它与仓库根目录及目标代码目录的 `AGENTS.md` 叠加使用。

本文件同时承担目录导航，不另设 `README.md`。它只规定阅读路径和不可违背边界，不复制各文档正文。

## 必读顺序

所有权限任务先读：

1. [产品与授权模型](01-product-authorization-model.md)：确认 Principal、Role、Effective Role、资源、action、scope 和 Ownership 语义。
2. [架构与信任边界](02-architecture-trust-boundaries.md)：确认 PEP/PDP/PAP、Core 事实源及 MatrixOne 数据权限边界。
3. 涉及业务功能权限接入、route/action 修改、权限缺陷或评审时，必读 [业务功能权限模型目录](08-business-permission-model-catalog.md)，确认接口对应的 resource/action、授权层级、Ownership 和依赖资源；再按需核对同前缀的 [Registry 快照](09-business-permission-model-registry.md)与[例外登记](10-business-permission-model-exceptions.md)。
4. 根据任务选择下表中的追加资料。

| 任务 | 追加阅读 |
| --- | --- |
| Backend -> Core API、Role transport、list/filter、membership-only、异步任务或 Worker | [请求与运行期合同](03-request-runtime-contracts.md) |
| Role/Member/Policy/Ownership 写入、邀请、审计、Saga、恢复或升级 | [存储、生命周期与审计](04-storage-lifecycle-audit.md) |
| 判断某能力当前是否已经接入、仍是例外还是已退休 | [实现状态](05-implementation-status.md) |
| 修改代码、测试、Registry、route 或本文档 | [验证与漂移控制](06-verification-drift-control.md) |
| Backend 公开 IAM API、Frontend bootstrap、错误 envelope 或 Product SDK | [公开 API、前端与 SDK 合同](07-public-api-frontend-sdk-contracts.md) |
| 新增或修改具体资源/action/scope/Ownership | [业务功能权限模型目录](08-business-permission-model-catalog.md)；同步核对 [Registry 快照](09-business-permission-model-registry.md)，例外边界只写入[例外登记](10-business-permission-model-exceptions.md) |
| 接入新 API 或修复既有权限路径 | 先核对 [业务功能权限模型目录](08-business-permission-model-catalog.md)，再读 [接入指南](integration-guide.md) 并执行仓库技能 [iam-integration](../../.agents/skills/iam-integration/SKILL.md) |
| M6 运行期权限延续 | [M6 运行期收口计划](plans/m6-runtime-enforcement.md) |
| M8 旧权限物理清理 | [M8 Legacy Hard Removal 收口计划](plans/m8-legacy-hard-removal.md) |
| 权限框架简化（评审中，未生效） | [权限框架简化方案](plans/permission-simplification.md) |
| 查阅已删除旧设计资料的迁移结果 | [旧资料迁移记录](legacy-source-map.md) |

## 事实优先级

权限事实发生冲突时按以下顺序处理：

1. 已确认的产品授权模型和本目录中的规范性边界。
2. Core canonical IAM Registry、Core Authorize/ResourceAccessFilter、canonical storage schema 和公开协议。
3. Backend/Core route contract、owner service、测试与生成清单。
4. 实现状态快照、Registry 派生快照和例外登记中的解释性内容。
5. [旧资料迁移记录](legacy-source-map.md) 中仅用于追溯的历史结论。

代码与规范不一致时，不能把当前代码自动视为正确，也不能按旧计划直接修改。先确认这是实现缺陷、文档漂移还是产品模型冲突；涉及产品行为、公开 API/SDK、资源/action 或 Role 模型变化时，必须先向用户列出影响和方案。

## 不可违背边界

- Backend 对外请求只提供未验证的 Explicit Role Candidate；只有 Core 校验 workspace、principal、direct binding 和 lifecycle 后产生的唯一 Verified Effective Role 可以参与 allow/deny。
- Backend、Catalog、Mowl、Worker 和运行时 handler 都是 PEP。Core `Authorize` 加 Shared Authorization Engine 是唯一 PDP；只有[请求与运行期合同](03-request-runtime-contracts.md)明确登记的 task-scoped 快照或短期数据面 capability 可以延续签发时准入，不能由业务路径自行新增。PAP 只负责校验、写入和发布 Application Policy。
- `Authorize` 与 `ResourceAccessFilter` 使用同一 PDP 内核和 canonical facts。不得使用 direct binding、角色并集、默认角色推断、legacy cache、system principal 或 system owner 形成本地 allow。
- `admin` 和 `superadmin` 是受保护的系统 Role。它们只有在成为当前 Verified Effective Role、且 Core 已验证 direct binding/lifecycle 后才参与请求；一旦生效，在 MOI 侧拥有全资源 Application IAM，并在 workspace 初始化时同步物化 MatrixOne 的全量数据库/表权限。它们不走普通 Role 的 DCL 拒绝/回收路径；durable task/job 可以延续创建时已可信确认的 workspace owner privilege-class。
- `runtime actor` 保存审计和运行身份，本身不是 capability。普通主体访问受控资源时仍需由 Core 重新校验冻结 Role 的当前 binding/lifecycle；已登记的 owner privilege-class 快照只在原 durable task/job 内有效，不能从 Role ID、`admin`、`system owner` 或异步外层上下文补出。
- 除已登记的 task-scoped 快照和短期数据面 capability 外，无法证明有效授权时不得放行。按[失败语义](01-product-authorization-model.md#9-失败语义)区分可控的无权限结果与不可控的系统故障，限制受影响操作并保留其它独立功能；不得把 `fail closed` 等同于统一报错或全局阻断。异常必须记录可关联的结构化诊断。

## 维护规则

- `business-permission-model-*` 是同一主题的三种视角：[业务目录](08-business-permission-model-catalog.md)定义产品语义，[Registry 快照](09-business-permission-model-registry.md)由 checker 对齐代码事实，[例外登记](10-business-permission-model-exceptions.md)只记录未进入 canonical 模型的当前边界。三者职责不同，不能互相替代或形成第二套运行期 Registry。
- 规范只描述已确认模型；当前接入状态只写入实现状态文档；未完成工作只写入 M6/M8 计划或[业务权限模型例外登记](10-business-permission-model-exceptions.md)，三者不得混写。
- 新增 workspace API、资源、action、Ownership 生命周期或异步受控访问时，必须先更新资源合同，再修改 Registry、PEP/PDP、测试和文档。
- 当前分支新增且未发布的错误契约或 API 直接更新全部调用点，不保留 legacy wrapper；已发布契约的兼容处理必须先确认。
- 旧权限表、PermissionService、permission code、角色并集和本地 allow fallback 只能删除或隔离，不能作为新系统依赖恢复。
