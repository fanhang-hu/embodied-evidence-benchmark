# E6 当前范围与运行入口

E6 的研究问题是：低信任 Producer 的证据如何进入 Planner 和最终授权，
以及证据来源、采集时间与运行时变更覆盖如何影响安全和任务效用。

**当前状态：限定范围验收通过。** 用户终端完成 16 回合在线 DeepSeek／Unity 闭环，
独立复审全部通过。结论和边界见 [E6 结项验收](../E6_ACCEPTANCE_20261025.md)。

已有 `00_scope` 至 `15_dataflow` 的源码与结果保持原样。此前 16 个正式回合是
T0 证据路由／任务恢复实验，不是生产者级攻击或线上重规划。新增实验单独记录。

## 当前已验证结果（原生推进后）

主矩阵使用 `runtime_v3.py`，新增关键动作 Fresh 基线使用 `runtime_v4.py`；
均支持检查点续跑，负的导航可见性标志不再
提前替代授权和原生动作回执。已完成且独立审计通过的批次：

| 批次 | 回合 | Planner | 场景范围 |
|---|---:|---|---|
| 正式开发矩阵 | 144 | 原始 DeepSeek 归档计划 | 8 个已有配置，4 个场景 |
| 字段权限／持续性压力测试 | 96 | 原始 DeepSeek 归档计划 | 两类合同；单／双字段，一次／持续 |
| 新场景矩阵 | 72 | 确定性 Planner | FloorPlan9/10，4 个配置、2 个场景簇 |
| 关键动作 Fresh 成本基线 | 24 + 12 | 开发集归档计划／新场景确定性 Planner | 与上述两条轨道逐配置匹配 |
| 新场景在线闭环 | 16 | 真实在线 DeepSeek | FloorPlan9/10；Shared／Independent Fresh |

[正式审计](../results/E6/24_runtime_audit/e6_runtime_development_v3_20261025_01/audit.json)、
[压力审计](../results/E6/24_runtime_audit/e6_runtime_stress_v3_20261025_01/audit.json)、
[新场景审计](../results/E6/24_runtime_audit/e6_runtime_heldout_symbolic_v3_20261025_01/audit.json)。
另有旧 v2 的 36 回合原生 Pilot，单独存放，不与正式矩阵合并算率。

在正式开发矩阵的持续成对污染条件下：

| 最终授权策略 | 攻击造成实际违规 | 无攻击合法任务完成 | 受保护查询（攻击／正常） |
|---|---:|---:|---:|
| Shared | 8/8 | 8/8 | 0 / 0 |
| Same-Source Fresh | 8/8 | 8/8 | 0 / 0 |
| Independent Fresh | 0/8 | 8/8 | 14 / 14 |
| Receipt Invalidation | 0/8 | 5/8 | 8 / 8 |
| Fail-Closed | 0/8 | 0/8 | 0 / 0 |
| Source-Aware Hybrid | 0/8 | 8/8 | 11 / 11 |

8 个配置不是 8 个独立场景。攻击被阻断不等于任务在攻击下恢复：本矩阵不重规划，
正常任务完成率单独测量。压力测试保留了一次性污染被后续真实发布纠正、
单字段污染被一致性检查暂缓的结果。关系任务可能在安全前缀就 DEFER，
未暴露危险候选时 UAR 为 `null`。

新场景中 Shared 与同源 Fresh 各实际违规 4/4，独立 Fresh 与 Hybrid 均为 0/4；
两者正常任务均完成 4/4。新场景使用确定性 Planner，不能称作 DeepSeek heldout。
攻击条件下 Hybrid 查询 6 次，独立 Fresh 查询 4 次，**Hybrid 没有普遍成本优势**。
开发矩阵的 Independent Fresh 每个候选均查询。后续已补齐“仅关键动作 Fresh”
成本基线，见下文；结果不支持 Hybrid 的查询成本优势。

完整分组指标、逐步消费到授权／执行时延及配对成本见
[原生分轨汇总](../results/E6/26_runtime_report/e6_runtime_v3_20261025_02/summary.json)、
[指标 CSV](../results/E6/26_runtime_report/e6_runtime_v3_20261025_02/metrics.csv)、
[配对成本 CSV](../results/E6/26_runtime_report/e6_runtime_v3_20261025_02/paired_costs.csv)。

当前 34 项针对性测试通过。旧 v2 扩展批次停留在 285 条记录且没有完整收尾，
包含导航标志导致的提前失败，保留在 `18_producer_native/e6_producer_matrix_v2_20261025_01`，
不纳入正式汇总。新场景最初的物理校准失败也保留：FloorPlan10 首个空炉头
因碰撞不可放置；修订规则在攻击前按固定次序选择首个通过物理校准的炉头，
未更换场景或按攻击效果筛选。

**在线 LLM 已验证。** 用户终端完成全部 16 回合，独立复审通过：攻击条件下
Shared 错误授权并原生违规 4/4，Independent Fresh 为 0/4；正常任务两组均完成 4/4。
两类合同分别为 Shared 违规 2/2、Independent Fresh 阻断 2/2。
[在线结果](../results/E6/36_online_report/online_20261025_170422_914231/summary.json)、
[独立复审](../results/E6/34_online_audit/heldout_durable_20261025_01/audit.json)。
当前在线入口使用带持久化调用账本的协议：
`results/E6/32_online_protocol/heldout_durable_20261025_01/protocol.json`。
它继承原 v3 在线协议的 16 个配置及顺序，增加失败停止、预算恢复与提供方配置冻结；
新旧协议均保留；正式轨道有 16 个不同的响应 ID，总用量 10,452 tokens。

属性攻击的假开关事实到达在线 Planner（4/4 攻击回合，含两种授权策略）；关系攻击
初始 Planner 关系事实仍为真（错误事实暴露 0/4），错误旧关系在评估器建立原生变更后
进入最终 Monitor。不能声称关系污染已经诱导 Planner 偏离。各策略独立调用模型，
本次 8 对配置实际提示和动作计划均相同，但这不是在线设计保证。

已按用户提示通过交互式 Bash 重新加载 `.bashrc` 并做一次真实请求复查：
密钥、地址和模型已加载且与冻结配置一致；本地 TCP socket 创建与 API 请求均返回
`errno=1`，没有收到 HTTP 响应。阻塞位于当前执行环境的网络权限，不能据此认定
用户接口或凭据不可用。[bashrc 复查记录](../results/E6/35_api_environment/bashrc_probe_20261025_01/summary.json)。
这些是历史环境诊断，保留原样；用户终端成功运行后，在线证据缺口已补齐。

## 关键动作 Fresh 补充与成本结论

新增策略只在合同定义的关键动作前，通过受保护 Controller 查询一次；
非关键动作沿用 Hybrid 的公开证据策略，无初始可信缓存。新增 24 个开发回合、
12 个新场景回合均完成并通过独立审计，覆盖正常、不安全无污染、持续成对污染三种条件。

| 轨道／条件 | 关键动作 Fresh 查询数 | 每步 Fresh 查询数 | Hybrid 查询数 |
|---|---:|---:|---:|
| 开发集／攻击 | 8 | 14 | 11 |
| 开发集／正常 | 8 | 14 | 11 |
| 新场景／攻击 | 4 | 4 | 6 |
| 新场景／正常 | 4 | 4 | 4 |

关键动作 Fresh 的攻击实际违规为开发集 0/8、新场景 0/4；正常任务完成分别为
8/8、4/4，正常任务无 BLOCK／DEFER。这里的新场景仍使用确定性 Planner。
在当前两类合同和任务序列下，更简单的关键动作 Fresh 已具有不高于 Hybrid 的查询开销；
Hybrid 保留为对照，不能作为“更省成本”的主要贡献。

[开发集基线审计](../results/E6/29_critical_fresh_audit/development_20261025_01/audit.json)、
[新场景基线审计](../results/E6/29_critical_fresh_audit/heldout_symbolic_20261025_01/audit.json)、
[成本补充汇总](../results/E6/30_critical_fresh_report/comparison_20261025_01/summary.json)、
[逐配置成本](../results/E6/30_critical_fresh_report/comparison_20261025_01/matched_costs.csv)。
对照复用已经审计的 v3 回合，要求初始合同事实、Planner 提示及计划动作匹配；
这些不是新增独立场景。补充基线在后续批次运行，时延只作描述，不能据此认定加速。
原始 `26_runtime_report` 保留补充前的报告，新成本判断以上述补充为准。

## 下一步与结项范围

新增[时序与完整性审计](../results/E6/31_trace_audit/supplement_20261025_01/audit.json)
已通过全部 348 个主轨道回合；覆盖计划截断、停止条件、实际消费消息、Fresh 查询区间、
原生提交日志和最终状态绑定，未改变现有实验结果。

当前验收范围为“自建 Producer 边界、两类冻结合同、归档／确定性／在线 Planner 下的
原生授权与防御成本验证”。新增在线回合也通过了时序与完整性检查，主轨道共 364 回合，
各轨道分开统计。范围内没有必需的未完成实验，见
[E6 限定范围验收](../E6_ACCEPTANCE_20261025.md)及
[机器可读验收记录](../results/E6/37_acceptance/scoped_20261025_01/acceptance.json)。

在线运行器 `online_runtime.py` 每批默认 4 回合，首个失败即停止；使用相同目录续跑
会核对既有结果与调用账本。已占用的调用槽位不重发，未提交结果的中断回合按未知结果
保留。`online_audit.py` 将账目核对与完整原生验证分开：未完成矩阵不公布完整矩阵率。
这些工程能力已通过故障测试，真实在线 API／Unity 闭环也已完成。

可联网终端的一键入口为 `bash /home/yyn/embodied/scripts/run_e6_online.sh`：
自动加载 `.bashrc`、核对配置、运行剩余回合，再审计和生成分组报告。
`--check` 仅检查本地环境，`--report-only` 仅核对与汇总已有数据。
历史[待运行状态报告](../results/E6/36_online_report/readiness_20261025_01/summary.json)
仍保留，不作为当前状态。当前无需再次调用 API；使用 `--report-only` 可复核现有数据。
报告区分 API／响应错误、Planner 空计划、Guard 拒绝和原生失败，并单独记录缺失 Token 用量。

若论文范围保持自建管线，部署级上游漏洞、并发原子授权和更多场景属于扩展研究；
只有声明这些能力时才需要相应证据，不将它们无限追加为本阶段结项前置条件。

## 前一轮离线结果

- 首轮 10 项针对性测试通过；包含真实 IPC 权限隔离与伪造来源检查，
  以及使用 Fake Controller 的编排／审计回归测试。Fake 回执不进入实验结果。
- [旧恢复实验统计补充](../results/E6/16_recovery_review/e6_review_v2_20261025_01/review.json)。
- [36 条 Pilot 离线审计](../results/E6/20_producer_audit/e6_producer_pilot_offline_v2_20261025_02/audit.json)。
- [576 条开发配置矩阵离线审计](../results/E6/20_producer_audit/e6_producer_matrix_offline_v2_20261025_01/audit.json)：
  8 个已有配置、两种字段权限、两种持续性、三个条件、六种授权策略。
  持续成对污染时，Shared 与同源 Fresh 各错误授权 8/8 个危险参考候选；
  独立参考证据均阻断。单字段持续污染被成对一致性检查暂缓；
  一次性污染在后续重新发布真实事实时被阻断。
- 首轮预检发现本地 Unix socket `bind()` 返回 `EPERM`，Xvfb 无法建立监听套接字。
  [环境检查与完整离线记录](../results/E6/19_producer_preflight/e6_producer_matrix_v2_20261025_01/preflight.json)
  保留了这一检查结果。但该检查未覆盖已安装 AI2-THOR 的 headless/FIFO 路径；
  后续已用这条原生路径运行，无需 Xvfb。离线结果仍不计为 Execution ASR 或任务完成率。

已执行的旧 v2 36 回合原生 Pilot 协议是
`results/E6/17_producer_protocol/e6_producer_pilot_v2_20261025_02/protocol.json`。
`...pilot_v2_20261025_01` 是开发过程中的旧冻结版本，依赖哈希已不匹配，
不可用于新执行；检查程序会拒绝它。576 条扩展协议在
`results/E6/17_producer_protocol/e6_producer_matrix_v2_20261025_01/protocol.json`。

## 本轮调整

- `recovery_review.py` 对旧结果补充统计：分别报告 4 个原生失败触发案例与
  4 个 BLOCK 触发案例；总受保护查询为 R1 24 次、R2 28 次；没有危险候选时
  UAR 为 `null`。旧汇总不覆盖。
- `producer_worker.py` 在受信初始化后安装 Linux seccomp syscall allowlist，
  再接收环境观察。Worker 只能通过继承的标准输入输出收发 JSON；文件打开、
  网络套接字和父进程控制均无权限。每次启动保存权限探测结果和进程标识。
- `producer_boundary.py` 是实际接收接口：同一 Producer 的发布和 Fresh 请求
  使用同一进程与管道。接收端验证字段权限，并通过管道绑定来源，
  不把消息内的 `source_id` 当认证凭据。Monitor 本体沿用冻结的确定性策略。
- `producer_experiment.py` 对照 Shared、Same-Source Fresh、Independent Fresh、
  Receipt Invalidation、Fail-Closed 和 Source-Aware Hybrid，分别使用真实的
  最终授权。提供单字段／成对字段、一次性／持续性污染参数。
- 原生矩阵包含无攻击合法任务、无污染不安全条件、Producer 攻击三类条件。
  关系任务执行原始计划前缀，再由评估器执行相同的原生关系变更；
  攻击者只能污染消息，不能执行变更。所有目标动作 `forceAction=False`。
- `metrics.py` 分开记录危险候选 UAR、episode 级错误授权、违规执行、
  正常任务误拒、各消费者事实传播率与可信关键证据覆盖。重复决策不视为
  独立案例。初始化、Producer 启动和实际消费至执行的计时分别报告。
- `producer_preflight.py` 只做归档候选的离线策略探测，确认 IPC、权限、计划
  来源和防御决策；不会执行计划前缀或 Unity 动作。它的受保护 Fresh 是
  离线参考快照，不能充当真实传感器证据。Execution ASR 与任务成功率留空。
- `producer_audit.py` 重建允许的字段变化、核对内容哈希、归档计划和决策。
  离线、原生回合分别验收，均不自动标记整个 E6 结项。

## 当前使用方式

使用已有可用环境，勿使用当前为零字节的
`/home/yyn/miniconda3/envs/exp-nodlink/bin/python`：

```bash
cd /home/yyn/embodied
export E6_PYTHON=/home/yyn/.conda/envs/ai2thor-eval/bin/python
export PYTHONDONTWRITEBYTECODE=1
"$E6_PYTHON" -B -m unittest discover -s tests -p 'test_e6_*.py' -v
```

先冻结一个包含两类合同的矩阵。以下新路径必须尚不存在；重跑使用新编号：

```bash
"$E6_PYTHON" -B -m e6_validation.runtime_v3 freeze \
  --out results/E6/22_runtime_protocol/my_pilot \
  --cases attribute_FloorPlan5_01 relation_FloorPlan6_02

env LIBGL_ALWAYS_SOFTWARE=1 "$E6_PYTHON" -B -m e6_validation.runtime_v3 run \
  --protocol results/E6/22_runtime_protocol/my_pilot/protocol.json \
  --out results/E6/23_runtime_native/my_pilot --limit 12
```

重复同一条 `run` 命令继续下一个批次，直至 `summary.json` 的 `next_index` 等于
`expected`。单个回合已提交的结果不覆盖；未完成尝试保留。使用已有 Controller
的 headless/FIFO 模式直接运行，无需 Xvfb。完整矩阵完成后再审计：

```bash
"$E6_PYTHON" -B -m e6_validation.runtime_audit \
  --run results/E6/23_runtime_native/my_pilot \
  --out results/E6/24_runtime_audit/my_pilot
```

冻结时不传 `--cases` 即选择原有全部 8 个开发配置，额外指定
`--modes single pair --persistence once persistent` 得到 576 个矩阵条件。
它们复用已有开发配置，不能称作独立 heldout，也不能与旧 T0 回合合并统计。

## 结项条件

1. **自建管线的 Producer 边界：** 独立进程、权限拒绝记录、原始输出、
   实际消费者、允许的字段清单均有证据。它证明实现的权限模型，
   不证明 SafeAgentBench 上游系统存在可被利用的低权限接口。
2. **攻击与最终授权：** 两类合同都要有完整的原生回合及独立审计；
   统计同源 Fresh 与受保护 Fresh 的实际授权和执行结果。
   单字段检查成功拦截或 Planner 不受影响都应保留为结果。
3. **通知边界：** 当前 Receipt/Hybrid 以受保护初始快照和受信单写者为前提，
   仅覆盖记录到的相关原生写入。它们不能证明初始低信任证据真实、
   静默漏报可检测、自然并发变更可阻止，或已实现原子授权与执行。
4. **效用与成本：** 无攻击合法任务单独报告；查询记录中包括所有初始化和
   授权查询。时延比较先按合同、条件、字段权限、持续性配对，
   失败／未完成回合保留，不把未暴露危险的回合算作零风险。
5. **在线补充与范围：** 新场景确定性 Planner 和 16 回合真实在线 LLM 闭环均已验证。
   两个新场景不等于广泛泛化。若声明部署级 T1，
   还需审计真实系统的 Producer 权限与传输，而非仅依赖本测试接口。

冻结源代码发生变化后，应重新冻结到新目录；不修改原协议以匹配新代码。

## 与已有工作的区别和剩余研究判断

ESTI 的 3.1.2 已明确将上游状态损坏作为假设，并未限定具体上游实现；
因此，单靠自建 Producer 输出污染不能主张首次提出这类攻击。
[ESTI v3](https://arxiv.org/html/2608.16806v3#S3.SS1.SSS2)

AGENTSAFE 也包含 SAFE-AUDIT，在生成详细计划前审查初始推理，不能将它
概括成仅有流程评测。当前核对的是 arXiv v3，未获得 CVPR PDF 全文。
[AGENTSAFE 4.4](https://arxiv.org/html/2506.14697#S4.SS4)

我们的可支持主线是：独立 Monitor 的最终授权仍可受同源假证据影响；
在显式受限的 Producer 权限下，受保护证据路径能恢复本实验合同的正确授权。
这是本实验的贡献定位判断，不是“首次”或已超过现有方法的证明。
