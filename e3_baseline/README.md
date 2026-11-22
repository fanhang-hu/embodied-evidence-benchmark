# E3 九项 baseline

顺序以原始 CSV 总览 #1–#9 为准。各项运行方法、环境、差异和局限在对应 README 中。

| 编号 | 目录 | 实现性质 | 主 Python 环境 |
|---|---|---|---|
| 1 | [b1_roboguard](b1_roboguard/README.md) | ADAPTED | roboguard-e3 |
| 2 | [b2_safegate](b2_safegate/README.md) | MECHANISM | ai2thor-eval |
| 3 | [b3_robosafe](b3_robosafe/README.md) | MECHANISM | ai2thor-eval |
| 4 | [b4_embguard](b4_embguard/README.md) | ORIGINAL_MODEL_AND_ADAPTED_FUSION | embguard-cpu |
| 5 | [b5_hdguard](b5_hdguard/README.md) | ADAPTED_AUXILIARY | refinement-gap-eval |
| 6 | [b6_selp](b6_selp/README.md) | ORIGINAL_COMPONENT_AND_MECHANISM | selp-ltl |
| 7 | [b7_percepttwin](b7_percepttwin/README.md) | ADAPTED_COMPONENT | percepttwin-eval |
| 8 | [b8_guardagent](b8_guardagent/README.md) | ADAPTED_SOFTWARE_AGENT_EMBODIED_NA | guardagent-eval |
| 9 | [b9_refinement_gap](b9_refinement_gap/README.md) | ADAPTED_COMPONENT | refinement-gap-eval |

所有原始结果保持原路径；各目录 `results` 链接供浏览。共享源代码、模型和 Unity 资源保留在 `external/`，以免破坏 editable 安装、缓存和交叉使用。b1/b9 共享 SPINE/RoboGuard，b4/b7 共享 Unity/PerceptTwin，不能计为相互独立的系统或样本。

`e3_baseline/*/run.sh --check` 只读检查；`--script` 在新工作区重跑。全量迁移表见 [path_map.csv](../organization_audit/path_map.csv)，研究评估见 [RESEARCH_REASSESSMENT.md](../RESEARCH_REASSESSMENT.md)。
