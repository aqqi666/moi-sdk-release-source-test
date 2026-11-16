# 请求身份与统一准入实施计划

目标是修复同一请求丢失 Effective Role、重新选择默认角色的问题，并移除通用权限入口的完整展示投影和重复事实读取。权限来源、资源/action、Core PAP 与独立数据边界保持[现有合同](../12-request-principal-admission.md)。

## 1. 批次与当前状态

用户已批准全量迁移。2026-09-22 本地实现位于 `codex/iam-request-context-design`；尚未部署或进行 QA 性能复测。

| 批次 | 最终实现 | 当前状态 |
| --- | --- | --- |
| P1 固定身份 | 私有字段 `VerifiedPrincipal`；准入后公共 PEP、batch、dependencies、service action、再授权和出站 body/header 使用同一个 Role；删除候选 accessor | 本地完成 |
| P2 Core 轻量验证 | 最小 `VerifyCurrentPrincipal`；canonical membership 先于 tenant 读取；Core attempt 复用原始事实，活跃请求计划保存已验证角色；保留未完成裁决所需 fence | 本地完成 |
| P3 首次业务裁决合并 | `Authorize` / `ResourceAccessFilter` 返回绑定身份；公共组件安装精确结果，数据树 filter 通过公共计划入口供后续 receiver 复用 | 本地完成 |
| P4 全量路由迁移 | 对象、集合、可信父资源、批量、Core PAP、数据边界、成员级、条件策略及 bootstrap 全部显式登记；移除旧注册入口 | 816/816 workspace 入口；canonical 288/288，未迁移 0 |
| P5 门禁与验收 | 类型构造边界、真实路由对账、拒绝时停止、角色固定、Core 事实计数与错误合同定向验证；更新文档和生成协议 | 本地门禁完成；CI 跨服务/版本组合及 QA 验收待执行 |

## 2. 公共机制与迁移范围

[WorkspaceAdmission](../../../moi-backend/pkg/iampep/request_admission.go)拥有启动时显式注册和首次 Core 调用；[VerifiedPrincipal](../../../moi-backend/pkg/ctxutil/verified_principal.go)拥有请求内不可变身份；[Core verifier](../../../moi-core/catalog/pkg/iamcore/principal_admission.go)复用原 canonical 角色规则。业务 handler 不选默认角色，不把 membership 投影当业务 allow。

Connector list 现在由一次 `ResourceAccessFilter` 完成身份验证与 `connector.read` 过滤；handler/service 消费该精确 plan，在 count/分页前应用 scope。空范围不查业务行，普通请求不再调用 `CurrentPrincipalRoles`。其它资源/action 仍独立裁决，不把“一次 RPC”推广成所有接口的硬性要求。

Core attempt fact bag 不跨 RPC、事务或裁决 attempt；snapshot retry 重建未完成裁决需要的事实。活跃 BFF 请求中的 Core 签名计划保存首次验证的角色与已完成精确数据范围，后续 Catalog 子请求复用它；请求中途撤权不追溯取消已授权范围，新请求重新验证。没有该计划的独立 Core 调用保留当前角色与 final fence 校验。任何路径都不能因角色撤销而替换默认角色。

需展示完整身份的三个入口各执行一次原投影，同时用于准入和响应。`CurrentPrincipalRoles` transport 已移除跨请求 singleflight 和响应关联 ID 重写，每个请求保留原始响应绑定和独立取消语义。

| 入口族 | 已实施内容 |
| --- | --- |
| Connector、Structured Connector、Task、Export、TraceSync | 集合 filter 合并；point action；任务父 Connector 最小解析；依赖 action 保留 |
| Runner、Sandbox、Executor Health、Compute、Model、Parser | 对象/集合准入；Health 保留两个资源 scope；平台 admin 仍用独立边界 |
| Workflow、Custom Operator、API Service、Workbook、Semantic Model、Dashboard | owner list、point action、依赖检查；execution 先只解析父 Workflow ID |
| Catalog、Data Share、SQL、Lineage | 固定身份；数据树匹配或补充 Core 请求计划，MatrixOne 遵守数据面合同；Root Volume 与批量资源保留可信 owner 解析 |
| IAM、Workspace Member、User Info、Audit | acting/target Role 分离；Core PAP 复合授权与事务 fence；bootstrap 投影复用；审计保留当前用户范围 |
| Agent、Session、Apps、Memory、DevTunnel 等独立 group | 复用同一准入机制，按现有 action、membership、条件策略和数据边界登记，不发明新权限 |

## 3. 覆盖与定向验证

实际 Gin 路由清单共 860 个 method/path 条目。其中 816 个 workspace 入口显式登记；44 个既有账号、platform-admin、provider callback、服务身份或 token 协议入口保留独立边界，逐条列在[覆盖门禁](../../../moi-backend/cmd/sdk-route-manifest/admission_coverage_test.go)，无通配排除。SDK `not_applicable` 不构成 IAM 排除。Core canonical route/action 清单 302 个 binding、288 个不同路由均已接入。

| 证据 | 覆盖内容 |
| --- | --- |
| [实际挂载路由拒绝测试](../../../moi-backend/cmd/sdk-route-manifest/admission_integration_test.go) | 813 个普通入口首次 Core 准入失败时，在 tenant DB、audit 和 handler 前终止；三个投影入口由 owner 专用用例验证 |
| [Connector 真链路](../../../moi-backend/pkg/handlers/dataconn/connector_admission_test.go)与公共集合/对象回归 | 显式 restricted、默认角色、all/restricted/empty、单次首裁决、过滤先于分页、不同 action 不复用；错误和畸形响应不进入业务 |
| [Principal projection](../../../moi-backend/pkg/handlers/iam/principal_admission_test.go)与 local/UC bootstrap | 单次投影、显式/默认 Role、身份/角色/关联绑定错误、失效身份拒绝 |
| Core verifier / fact bag / owner plan 测试 | membership 先于 tenant、direct binding/lifecycle、并发/取消、固定 Role 重试、新 attempt 和 final fence |
| [准入与 Catalog 请求计划衔接](../../../moi-core/catalog/pkg/iamcore/principal_admission_catalog_plan_test.go) | Verify、合并 Authorize/filter 保留角色来源与版本；下一请求感知撤权；首次集合范围跨子请求复用、Owner ID 冻结；point 与新 action 仍需 Core 裁决 |
| Backend/Core 结构检查 | 删除候选 getter；AST 限制 Verified 构造边界；实际 canonical action/resource 对账；公共 middleware 顺序 |
| SDK route alignment | 实际 Gin ↔ 源码 AST ↔ Go/Python SDK 三方对账；扫描 typed admission 注册器及封闭 method/path 循环，保留原 SDK 暴露范围 |
| 公开错误合同 | 状态/稳定 code、中英文展示、raw cause 脱敏与受控日志；未知路由、缺失身份和不完整响应 fail closed |

本地仅执行本次改动相关的定向测试、AST 门禁和轻量静态检查，不执行全应用、全模块或浏览器回归。协议使用 `make proto` / `make proto-python` 生成；Catalog API 与 Core SDK 文档由既有生成器更新。

相关 Backend、Core、SDK 包的 `go vet` 已通过；公共身份/PEP、IAM/成员投影和路由清单相关包的 `staticcheck` 已通过。额外检查 main/middleware 时，仍有既有 nil 指针与未使用赋值告警，本次不扩大到这些基线问题。

完整文档生成在 sparse checkout 缺少 Go Worker 目录时停止，完整文档校验还需要 Java 17；本次 API/SDK 生成步骤和文档代码片段检查已通过，未保留缺少 Worker 目录导致的无关空清单。

## 4. 发布顺序与回退

1. CI 执行全量权限矩阵、真实 MatrixOne、跨服务和新旧版本组合。特别验证旧 Backend/新 Core、新 Backend/旧 Core 的确定性失败语义，以及数据树/MatrixOne 不继承 BFF allow。
2. 先发布包含最小身份响应和合并协议的 Core，再发布消费方 Backend；不可依据 protobuf 可忽略未知字段推断旧 Core 可支持新准入。
3. QA 使用同一 workspace、数据量、角色、分页和并发采集 RPC/SQL 计数与 p50/p95，分别观测 IAM、业务 SQL、连接池等待和网络。对比 2026-09-21 的 2,101 ms / 4,879 ms 样本，不能将单样本换算成优化倍数。
4. 角色改变、范围扩大、缺失身份仍进入业务、未覆盖数据范围绕过 Core、未完成裁决所需 fence 缺失或未知 route 放行时停止发布并回退。已完成的请求计划精确复用属于预期行为。回退目标必须已修复固定角色，不能退回空角色重选默认版本。

部署回退是发布操作；请求内无自动 fallback。统一准入复用既有 Core 签名请求计划，没有新增跨独立请求缓存或持久化权限数据，因此无缓存失效、回填或票据回收任务。当前完成的是本地实现与门禁，QA 的实际耗时改善仍待部署后证明。
