# 具身智能：World State 污染与运行时安全验证

最新研究方案是 [Proposal-3](share-pool/Proposal-3.md) 和 [exp-5](share-pool/exp-5.md)。E1–E3 代码和证据已整理；E4 见 [E4 报告](results/E4/04_validation/e4_report.md)。E5 已完成限定 T0 范围的验收，见 [E5 验收](E5_ACCEPTANCE_20261025.md)。E6 已通过自建管线限定范围验收：144 回合正式矩阵、96 回合压力测试、72 回合确定性新场景验证、36 回合关键动作 Fresh 补充及 16 回合真实在线 DeepSeek 闭环均通过独立审计。在线 Shared 实际违规 4/4，Independent Fresh 为 0/4，正常任务两组均完成 4/4；成本结果不支持 Hybrid 优于关键动作 Fresh。见 [E6 结项验收](E6_ACCEPTANCE_20261025.md)及 [E6 说明](e6_validation/README.md)。此前整理的研究判断见 [RESEARCH_REASSESSMENT.md](RESEARCH_REASSESSMENT.md)。

`results/E4/00_inventory/` 的早期候选审计保留；新增 E4 证据位于 `00_ingress/`、`01_feasibility/`、`02_pairs/`、`04_validation/`。当前攻击明确为受控副本（T0），未证明原生低权限漏洞。

后续 [Wrong-Burner 补充](results/E4/04_validation/llm_shadow_and_binding_20261022.md) 已收缩目标绑定结论：父容器成员关系不能证明唯一物理落点。用户本机完成的 [DeepSeek shadow 复核](results/E4/04_validation/fp2_llm_shadow_result_20261022.md) 发现属性单例跳过关火，关系单例未出现危险提案；未接入 Monitor/Executor。记录在 `results/E4/03_llm_shadow/fp2_live_retry_01/`。

最新已完成 [FloorPlan2 属性案例五组归档 LLM 计划 / Unity 回放](results/E4/05_llm_closedloop/README.md)：Shared 的危险计划被错误授权并原生执行成功，Planner-only 和可信重查均拦截同一计划，Clean 危险初态与 Benign 安全初态正常完成。证据位于 `results/E4/05_llm_closedloop/`，限定 T0 研究者适配系统，未证明原生漏洞。

## 目录

```text
e1_validation/                  E1 机制验证、M1 通道隔离、M5/M6 厨房状态入口
e2_validation/                  E2 历史/视觉/可信重查/TOCTOU 简单防御
e4_validation/                  E4 原生链路审计、两类事实、真实配对与验证
configs/exp5/                   E4 冻结攻击权限、安全政策、Pilot 配置
setup_checks/                   M0 平台、技能和稳定性检查
e3_baseline/
  b1_roboguard/
  b2_safegate/                  SafeGate-inspired，M 级
  b3_robosafe/                  RoboSafe-inspired，M 级
  b4_embguard/                  官方模型与研究者视觉融合
  b5_hdguard/                   HomeSafe-Bench 辅助告警轨道
  b6_selp/                     官方符号组件与研究者环境映射
  b7_percepttwin/               规划/仿真/后审计适配组件
  b8_guardagent/                软件 Agent；具身核心比较 N/A
  b9_refinement_gap/            SPINE/RoboGuard 轨迹与共享图组件评估
experiment_tools/              路径初始化，不含新的安全策略或模型
scripts/                       统一启动与整理验证工具
external/                      共享上游源码、模型、数据与 Unity 资源
results/                       原始结果；保留历史路径与内容
share-pool/                    用户研究材料与原始 CSV/XLSX
organization_audit/            原代码备份、迁移表、依赖快照、验证记录
```

九项编号与 `baseline.csv` 总览完全一致。[E3 总索引](e3_baseline/README.md) 链接到九份包含环境、执行命令和局限分析的 README。`baseline.xlsx` 五张表均已读取，总览与 CSV 的非空单元格顺序一致；后半段说明存在旧状态，见 [表格审阅](organization_audit/baseline_workbook_review.md)。

## 检查与运行

```bash
cd /home/yyn/embodied
python3 scripts/verify_layout.py
bash e3_baseline/b1_roboguard/run.sh --check
bash e3_baseline/b1_roboguard/run.sh --list

# 一个已有证据上的 Spot 离线重放，不调用 API、不启动 Unity
bash e3_baseline/b1_roboguard/run.sh \
  --script e3a3_offline_replay.py \
  --fresh-result E3/01_roboguard/e3a3_offline_replay.json
```

`--check` 只检查 Python、关键依赖导入和证据存在性，不等于官方系统完整复现。`--script` 自动使用该方法的实际解释器，并建立 `/tmp/embodied-run-*/workspace`：复制历史结果作为输入，在复制的代码和结果上运行，保留原始证据。可用 `--work-dir /tmp/unique-run-name` 指定尚不存在的目录。日志开头打印实际工作区，后续产物从该目录查看。

原脚本有防覆盖和断点续跑行为。要真正重算某个结果，按各 README 使用 `--fresh-result <相对 results 的路径>` 清除工作区里的对应副本；源目录文件不受影响。脚本自己的参数放在 `--` 后。仿真入口加 `xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1` 前缀，API 入口使用原有环境变量，不在文件中写入密钥。下载/安装脚本和历史生成器仍保留，但日常直接运行已生成入口。

也可以 activate 对应环境后直接 `python e3_baseline/.../<脚本>.py`；路径初始化会切回项目根目录。**直接运行沿用原脚本的输出位置和覆盖策略**；推荐使用统一启动器保留旧证据。Conda/venv、上游源码和权重没有移动；各 baseline 的 `upstream/` 和 `results` 为相对软链接，指向唯一共享存储。

## 迁移与可复现性

- 共归类 228 个源文件（226 个 Python、1 个 shell、1 个历史备份），早期 E1/M1/M5/M6 已按功能重命名。E2 用目录明确阶段，保留 B1–B7 子实验编号。
- [path_map.csv](organization_audit/path_map.csv) 给出旧路径、新路径、整理前后 SHA256；[original_code.tar.gz](organization_audit/original_code.tar.gz) 保存修改前源码。历史材料中的旧命令通过迁移表定位，原文未覆盖。
- [环境快照](organization_audit/environments/) 同时保留 pip、Conda 元数据及实际导入检查。SafeGate 的 Z3 是历史 `pip --target` 本地依赖，启动层单独恢复路径；EMBGuard 使用独立 CPU venv。
- [整理验证](organization_audit/VALIDATION.md) 记录此次实际跑过的离线检查。原始 907 个结果/材料文件用 SHA256 逐项核验；本次验证未重跑远程模型或危险仿真动作。

根目录的旧 `Proposal-2.md` / `exp-2.md` 以及历史截图、`diskcache8` 暂作原始归档；最新文字依据始终是 `share-pool/`。`external/` 中有大型 Unity/资产目录，不能仅因当前某个 baseline 没用到就删除。
