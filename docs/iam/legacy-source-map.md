# 旧权限资料迁移记录

`docs/design/permission/` 已在新 IAM 文档验收后删除。本文件只记录删除前资料如何处理，帮助通过 Git 历史追溯来源；它不定义当前权限规则，也不要求恢复任何旧文件。

状态含义：

- `current-source-migrated`：仍有效的事实已迁入新文档，后续以新文档和当前代码为准。
- `historical-discarded`：只描述决策背景、阶段或旧实现，删除时没有迁入当前规范。
- `retired`：描述的生产机制已删除，不得恢复。

| 旧资料 | 状态 | 新位置/说明 |
| --- | --- | --- |
| `README.md`、`AGENTS.md`、`contracts/README.md` | `retired` | 导航职责由 `docs/iam/AGENTS.md` 承担 |
| `00_moi_permission_refactor_requirements_and_scenarios.md` | `current-source-migrated` | 产品不变式迁入 `01`，阶段描述没有迁入 |
| `01_moi_permission_refactor_legacy_architecture_analysis.md` | `historical-discarded` | legacy 背景；旧 allow 路径不得恢复 |
| `02_moi_permission_refactor_mo_rbac_dcl_alignment_research.md` | `current-source-migrated` | 当前 Application IAM/MatrixOne 边界迁入 `01`、`02` |
| `03_moi_permission_refactor_role_inheritance_reuse_research.md` | `current-source-migrated` | 当前 Role graph 合同迁入 `01`、`02`、`04`；研究过程删除 |
| `03a_moi_permission_role_graph_read_model_research.md` | `current-source-migrated` | 单快照、边界和版本合同迁入 `02`、`04`、`06` |
| `04_moi_permission_refactor_solution_selection.md` | `historical-discarded` | 选型过程；当前架构见 `02` |
| `05_moi_permission_refactor_architecture_design.md` | `current-source-migrated` | 当前边界迁入 `01` 至 `04` |
| `07_moi_permission_refactor_integration_guide.md` | `current-source-migrated` | 迁入 `03`、`integration-guide.md` |
| `08_moi_permission_refactor_frontend_api_design.md` | `current-source-migrated` | 有效语义迁入 `03`、`07`；旧 DTO 草案不作为事实源 |
| `09_moi_permission_refactor_core_authorize_contract.md` | `current-source-migrated` | 迁入 `02`、`03` |
| `10_moi_permission_refactor_m5a_sql_effective_role_connection_plan.md` | `current-source-migrated` | 当前 SQL contract 迁入 `03`、`04` 和 `08-business-permission-model-catalog.md` |
| `10_moi_permission_resource_model_catalog.md` | `current-source-migrated` | 业务功能/action/授权层级和领域边界迁入 `08-business-permission-model-catalog.md`；代码集合快照与当前例外分别由同前缀的 `09`、`10` 维护 |
| `13_m7_product_frontend_alignment.md` | `current-source-migrated` | Current Principal bootstrap、capability gate 和验证分层迁入 `03`、`05` 至 `07` |
| `backend_legacy_permission_inventory.md` | `retired` | 删除前用于证明 Backend legacy 范围 |
| `frontend_legacy_permission_inventory.md` | `retired` | 删除前用于证明 Frontend legacy 范围 |
| `contracts/m0_storage_rollout_contract.md` | `current-source-migrated` | 当前 storage/lifecycle 合同迁入 `04`、`06` |
| `iam_resource_lifecycle_operations_runbook.md` | `current-source-migrated` | 有效运维边界迁入 `04`、`06` |
| `resource_lifecycle_reliability_audit.md` | `current-source-migrated` | 有效审计结论迁入 `04`、`06`；旧问题列表删除 |
| `stages/06_moi_permission_refactor_implementation_plan.md` | `current-source-migrated` | 未完成 M6 迁入 `plans/m6-runtime-enforcement.md` |
| `stages/11_m4a_legacy_containment_plan.md` | `retired` | M4a 阶段产物 |
| `stages/12_m8_legacy_permission_hard_removal_plan.md` | `current-source-migrated` | 已完成事实迁入 `04`、`05`；未完成项迁入 `plans/m8-legacy-hard-removal.md` |
| `stages/iam_m0_storage_rollout_stage_plan.md` | `current-source-migrated` | 有效存储、版本和事务合同迁入 `04`、`06` |
| `stages/iam_m1_core_store_pdp_stage_plan.md` | `current-source-migrated` | PDP、Grant Index、Role Graph 和审计合同迁入 `01`、`02`、`04`、`06` |
| `stages/iam_m2_core_services_stage_plan.md` | `current-source-migrated` | 管理服务与公开 View/Grant 合同迁入 `04`、`07` |
| `stages/iam_m35_production_contract_boundary_stage_plan.md` | `current-source-migrated` | Backend/Core PEP/PDP 合同迁入 `02`、`03`、`06` |
| `stages/iam_m3_backend_thin_pep_stage_plan.md` | `current-source-migrated` | Thin PEP 与错误合同迁入 `02`、`03`、`07` |
| `stages/iam_m5b_matrixone_data_privilege_stage_plan.md` | `current-source-migrated` | DataPrivilege、DCL recovery 和 session 边界迁入 `04` 至 `08` |
| `stages/iam_m7_frontend_integration_stage_plan.md` | `current-source-migrated` | Current Principal、前端上下文和验证分层迁入 `03`、`05` 至 `07` |
| `stages/iam_resource_lifecycle_reliability_remediation_plan.md` | `current-source-migrated` | durable operation、readback 和 recovery 合同迁入 `04`、`06` |

旧资料中的 M0-M8 时间线、PR checklist、未来 cache/secondary role/Definer Rights/clone 等建议没有迁入当前规范。需要重新启用其中任何能力时，必须以当前实现和产品需求重新设计。
