# M8 Permission Model Hard Removal 收口计划

本文只跟踪新权限主链路生效后仍未完成的 legacy 物理清理和发布验收，不重新定义授权模型。授权规范以 [产品与授权模型](../01-product-authorization-model.md)、[架构与信任边界](../02-architecture-trust-boundaries.md) 和 [存储、生命周期与审计](../04-storage-lifecycle-audit.md) 为准。

## 1. 已闭环基线

- Core `Authorize` 与 Shared Authorization Engine 是唯一 Application IAM PDP。
- direct binding/system-role shortcut、角色并集、permission code、对象 ACL 和 legacy cache 不再产生 runtime allow。
- Offset110 已实现 owner-only reset、旧权限表删除、MatrixOne 用户/Role/grant readback 和 durable operation 终结，并有 latest-upgrade fixture。
- 旧 Core Role/permission handler、SDK/CLI facade 和 410 tombstone 已删除；旧 URL 返回 404。
- 当前 `service/permission` 只承担 workspace bootstrap、系统 Role/MatrixOne materialization 和邀请 Role 校验。包名本身不是 legacy allow 证据，不得在没有替代 owner 的情况下删除这些当前能力。

上述事实不等于 M8 已全部完成。M8 只有在下列清单全部关闭后才能从 `cleanup-gap` 改为 `retired`。

## 2. 待收口清单

### 2.1 公开成员 Role 兼容入口（已完成）

成员 Role 更新已完成 breaking clean-break，所有调用方统一迁移到 canonical workspace IAM Role Binding API（`GET/PUT /newmoi/workspaces/{workspace_id}/iam/users/{user_id}/role-bindings`）。请求显式携带 assigned/default Role、binding/default CAS version 和 request ID；清理 Default Role 必须显式传 `clear_default_role=true`。

| 层级 | 当前 owner / 证据 |
| --- | --- |
| Backend route | `moi-backend/pkg/handlers/iam/iam.go` 注册 canonical GET/PUT route，权限为 `workspace_member.read` / `workspace_member.role_binding.mutate` |
| Go Product SDK | `sdk/go-sdk/iam.go` 的 `IAMService.UserRoleBindings` / `PutUserRoleBindings`，请求和结果类型来自 `sdk/proto/product/iam.proto` |
| Python Product SDK | `sdk/python-sdk/moi_product_sdk/client.py` 的 `IAMService.user_role_bindings` / `put_user_role_bindings`，请求和结果类型来自同一 Product proto |
| 回归与对齐 | `moi-backend/cmd/sdk-route-manifest`、`sdk/route-alignment`、Go/Python IAM transport tests 验证 canonical route、字段和双语言映射；旧 DTO、route matrix、SDK/CLI surface 与 fixture 已删除 |

Issue #15015 的成员 Role clean-break 验收已关闭：旧 Backend route/DTO/manifest/API matrix、Go/Python SDK 方法、CLI 命令、文档和测试 fixture 均已删除；canonical API 的 admin assign/unassign/default、superadmin owner-only、CAS conflict 和 Core unavailable 合同继续由 IAM tests 覆盖。不得新增 wrapper 或数组首项 Default Role 推断。

### 2.2 Legacy 物理资产与验证边界

Legacy 物理清理是 M8 的一次性迁移验收，不建立全仓 retired path 清单或专用 permission CI 作为长期约束。现有 `iam_canonical_boundary_check.py` 继续约束活跃的新 IAM package 不得依赖旧 allow 路径，但不承担全仓 retired asset inventory。

本次已完成 Core duplicate role-create 入口收口：删除 `/api/v1/system/iam/roles/create` route、handler/interface、旧 mutation create service/storage 方法与旧 `RoleCreateRequest/RoleCreateResponse`，`moi-backend/pkg/coreiam/roles.go` 和 Core canonical IAM integration/route tests 已统一使用 `/api/v1/system/iam/role-create`；`moi-core/docs/api/catalog-api.md` 已重生成，旧路径由 404 回归测试锁定。下列 2.2 其余 legacy 物理资产和 2.3 真实环境验收仍未关闭。

仍需完成：

1. 枚举 Backend、Core、Catalog、Frontend、Product SDK、CLI、测试和文档中的旧 permission table、permission code、对象 ACL、角色并集和旧 route consumer。
2. 删除只被测试引用的旧 schema helper 中 `role`、`role_priv`、`role_grant`、`user_role` 定义及对应测试；fresh schema 不得重新创建 Offset110 已删除的旧表。
3. 修正仍把 `role_permissions`、`moi_object_permissions` 等描述为当前授权事实的 Core 文档。

完成上述清理后，删除只服务于 permission consistency 或 retired-asset 枚举的 checker、测试和 workflow 入口，不再用新的 meta-guard 维持它们的缺席。后续提交中的无生产调用方陈旧代码由智能体 harness 引导和 code review 把关；生产授权回退仍必须由 canonical IAM 的行为测试、集成测试和升级测试覆盖，门禁以实际调用链及 allow/deny 合同为准，不以历史文件名集合为准。

不可误删：

- canonical `roles`、`user_roles`、Application Policy、Ownership 和 audit 表；
- MatrixOne `mo_role`、`mo_role_grant`、`mo_role_privs` 等当前 DCL 事实；
- 为支持历史升级而必须保持不可变的旧 offset handler；
- 当前系统 Role materialization 和邀请 Role 校验实现。

### 2.3 发布验收证据

现有 `moi-frontend/apps/moi-app/e2e/iam/iam-role-management.spec.ts` 是 mock E2E，只证明浏览器交互、canonical route 和错误展示。M8 仍需可重复的真实 Backend/Core/MatrixOne 验收：

1. workspace owner 的 Verified Effective Role 为 `superadmin`，受邀协作者的默认 Role 为 `admin`；非 owner 无法取得或绑定 `superadmin`。
2. 系统 Role 的 metadata、lifecycle、policy 和 inheritance mutation 均被 Core 拒绝，展示名不参与判权。
3. 当前选择受限 Role 时不能因另有 admin binding 被放行；切换为 admin 后 Application IAM 才按系统 Role 规则允许。
4. DataPrivilege 的 View/Validate/Apply/Operation 与实际 SQL allow/deny、撤权和 capability gate 在真实 MatrixOne 上一致。
5. Offset110 latest-1 升级、重启恢复、外部事实 readback 和 fresh tenant 不创建旧权限表均有 gate 证明。

当前产品不开放绕过 IAM capability gate 的自由创建 Role；受限 Role 创建入口的浏览器交互只覆盖 `provisioning_state=ready` 的成功路径，不替代本节真实 Backend/Core/MatrixOne 验收，也不能恢复旧计划中的无约束自定义 Role 入口。failed provisioning 的 retry/recovery 不在本节范围内。

## 3. 实施顺序

1. 先完成全仓 consumer 与 schema inventory，区分 current canonical facts、不可变历史 offset 和可删除 legacy 资产。
2. 删除无生产 consumer 的物理资产并完成一次性清理验收，不新增专用 retired permission-code 或 retired-path inventory gate。
3. 跑真实 IAM/DataPrivilege 与 Offset110 gate，保存可重复命令和结果。
4. 更新 [实现状态](../05-implementation-status.md)；只有全部验收成立后将 M8 标记为 `retired`。

## 4. 非目标

- M6 的 Worker、retry/resume 和逐依赖动态重验继续由 [M6 计划](m6-runtime-enforcement.md) 跟踪。
- `embedding_results` 等非 IAM 业务表不属于 M8。
- 不借 hard removal 改写产品 Role 模型、开放自定义 Role 或新增兼容层。
- 不恢复 retired PermissionService、permission code、本地 allow fallback 或 system credential fallback。
- 不为已删除的 permission 文件名、目录或 CI 接线建立永久 denylist/meta-guard。
