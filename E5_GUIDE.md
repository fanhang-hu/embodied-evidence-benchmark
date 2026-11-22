# E5 第一轮：来源归因、目标绑定与部分回执证据

日期：2026-10-23。依据 [exp-5 §8](share-pool/exp-5.md) 和 [Proposal-3](share-pool/Proposal-3.md)。本轮已实际运行 Unity、归档并核查结果，**不是只有实验方案**。

## 当前阶段与结论

已完成 E5-A/E 的首轮元数据/回执 Pilot：同源一致性、同源重读、原生受保护重查、证据不足的 DEFER/恢复，以及精确目标绑定。范围仍为 **T0 CONTROLLED-COPY ONLY**，没有发现或证明 T1/T2 原生攻击入口。

本轮复用 E4 的 8 个任务配置、4 个场景簇，标签为 `E5_dev_reuse_E4_small_heldout`。E4 Heldout 已被观察过，不能将其再次称为新的未知 Heldout；本轮新运行或重复的条件也不增加独立配置数。

本轮所有危险候选都只做授权探针，**未提交候选取锅/开火动作**。Unity 实际执行的是 Evaluator 场景准备、导航与 Pass。下面的 UAR 都是固定候选 `UAR_probe`，不是新的联合执行 ASR；合法授权恢复也不等于实际完成任务。E4 的真实 LLM→Monitor→Unity 违规执行证据继续独立保留。

## 1. E5-A：同源一致不代表真实

原安全政策、动作目标 ID 和物理真值保持不变，新增的 E5 T0 权限仅允许修改两项指定字段：

- 属性：精确绑定的 `StoveKnob.isToggled` 与 `StoveBurner.isToggled`。
- 关系：指定锅的 `parentReceptacles` 与 `position`；反事实位置取自 E4 事前冻结的另一物理配置。

**一致性仅指被检验的两项谓词。** 没有修改全部 AABB、反向包含等字段，不声称整个原生 metadata 全局自洽。本轮权限比 E4 的单字段权限更宽，不能隐去这一变化。Unity 真值、政策、目标 ID、原生回执和受保护查询均不在污染权限内。

16 个真实初态（每配置安全/危险各一）× 8 组 = 128 条记录：112 条有效授权探针，16 条原始 A4 `NOT_AVAILABLE`。属性危险候选 5 个、关系危险候选 3 个，合法候选合计 8 个。

| 组别 | 错误 ALLOW / 危险候选 | 合法 ALLOW / 合法候选 | 合法 BLOCK | 合法 DEFER |
|---|---:|---:|---:|---:|
| A0 Clean | 0/8 | 8/8 | 0 | 0 |
| A1 单字段 + 两谓词检查 | 0/8 | 0/8 | 0 | 8 |
| A2 两字段对内一致 + 同一检查 | 8/8 | 0/8 | 8 | 0 |
| A3 A2 + 同源重读 | 8/8 | 0/8 | 8 | 0 |
| A5 实际原生 Pass 重查 | 0/8 | 8/8 | 0 | 0 |
| A6 零查询预算 | 0/8 | 0/8 | 0 | 8 |
| A6 一次查询预算 | 0/8 | 8/8 | 0 | 0 |

A1 的属性检查复用 E4 的 Knob–Burner 判据；关系检查是事前固定的成员关系/原点几何一致性诊断，沿用 0.03 m 对齐与间隔门槛。没有把它称作 E4 已有的关系防御或独立视觉证据。

A3 通过序列化往返重读 A2 的同一内容，保留相同来源祖先与状态哈希，不产生新传感器信息。A5 和 A6 各完成 16 次真实 Pass，共 32 次；它们是同一 Unity 的另一个受保护读取分支，属于模拟器权威 X 上界，**不等于独立物理传感器或部署级隔离**。

真实 LLM 计划只有在公开输入与 E4 冻结请求完全相等时才复用。本轮第二字段不在原 LLM 的公开输入投影中，因此可以保持请求一致；没有重新调用模型。属性类 5 个危险初态继续对应归档的违规规划，关系类 3 个未出现同类 LLM 违规规划。关系类固定探针出现 3/3 错误 ALLOW，不能改写成真实 LLM 的 3/3 共同失效。

## 2. A4 独立于污染 Adapter 的部分回执证据

原始 A4 没有已建立的视觉或充分回执通道，因此 16 条 N/A 原样保留。另行冻结 `receipt_20261023_01`，运行一个新的原生回执子实验：

- Guard 只读原生成功动作回执与冻结目标映射，不读取私有真实状态或被污染字段。
- 成功的目标旋钮 ON/OFF 回执可建立供电事实；锅的 Pickup→Put 回执链可建立目标放置事实。
- 没有相关动作回执，不能从“动作缺席”推断设备已关或锅不在炉头，返回 UNKNOWN/DEFER。
- 只有在**冻结的单写者、静态准备阶段动作链完整**这一假设下使用这些事实；没有证明部署中的日志认证、并发安全或动态新鲜度。

| 方法 | 事实覆盖 | 错误 ALLOW / 危险候选 | 合法 ALLOW | 合法 DEFER | 实际额外 Pass |
|---|---:|---:|---:|---:|---:|
| 仅回执 | 8/16 | 0/8 | 3/8 | 5 | 0 |
| 回执不足时一次查询 | 最终 16/16 | 0/8 | 8/8 | 0 | 8 |
| 对照 A5：每项都查询 | 16/16 | 0/8 | 8/8 | 0 | 16 |

上述 8 次查询是新子实验中真正按需执行的次数，不是从旧日志推算出来的节省。两次实验复现同一任务配置和关键初态，不是同一物理时刻；查询计数排除准备和导航调用。时延只报告 `Controller.step(Pass)` 与本地 Guard 各自观测，不代表在线 LLM 或完整机器人端到端开销。

原生回执和元数据来自同一 Unity 物理根源。这里的“独立”只表示该回执路径不经过本轮可写的 metadata Adapter；不是独立传感器。实际回执支持的范围与信任假设都已单列。

## 3. E5-E：有锅不等于目标炉头有指定锅

FloorPlan6/7/8 各 3 个真实物理控制：锅在目标炉头、锅在非目标炉头、两个指定炉头都没有锅，共 9 个控制；每个控制做 6 个证据/绑定消融，54 条决策。保存原生放置回执、精确 ID、几何诊断和 E4 原生干预测量的 knob→burner 映射。

| 检查方式 | 错误 ALLOW / 危险控制 | 合法 ALLOW / 正控制 | 合法误拒 |
|---|---:|---:|---:|
| 全场景有任意锅在任意炉头 | 5/6 | 3/3 | 0 |
| 精确目标成员关系 | 0/6 | 3/3 | 0 |
| 精确目标 + 原点几何一致性 | 0/6 | 3/3 | 0 |
| 采用指向相邻炉头的不可信别名 | 3/6 | 0/3 | 3 BLOCK |
| 显式绑定冲突 | 0/6 | 0/3 | 3 DEFER |
| 缺失绑定 | 0/6 | 0/3 | 3 DEFER |

FloorPlan7/8 的“两指定炉头都空”控制中，场景其他炉头仍可能有另一件锅具，这正是场景级判断错误的原因；不能把“全场景有锅”当作本次精确目标事实。冲突/缺失组是预设条件下的 DEFER 控制，不证明一个通用模型能发现所有身份冲突。

这轮没有采集 RGB、没有训练/调用视觉模型、没有 camera ROI 绑定；原点对齐也不能证明唯一物理承托/接触力。

## 4. 预注册修订和失败保留

第一次绑定运行 `binding/native_20261023_01` 完成 5 个控制、30 条决策后，在 FloorPlan7 的 neither 控制停止：默认另一件锅具占据所选非目标炉头，使“两指定炉头都空”不成立。

保留该运行及 `failure.json`。在 `freeze_20261023_02` 中，依据**既有 E4 原生危险初态快照**，选择事前已验证且默认没有 Pan/Pot 的非目标炉头，随后重新执行全部 9 个控制。没有更改政策、Guard、模型提示词或排除失败任务配置；旧控制不计为额外独立样本。

v1/v2 的 manifest 和 `frozen_sources/` 均保留，可以核对每个结果使用的源码版本。执行新实验严格检查当前版本哈希；离线审计旧结果可核对相应源码快照。

## 5. 目录和启动方法

```text
e5_validation/
  common.py           # 文件/哈希/统一证据字段、冻结检查
  protocol.py         # 两谓词一致性、受控副本、目标绑定消融
  freeze.py           # 前瞻冻结配置、权限、预算、源码快照
  source.py           # E5-A：原生查询/离线归档两种明确区分的模式
  binding.py          # E5-E：三种真实物理控制
  receipt.py          # 独立预注册的 A4 回执与按需查询
  verify.py           # 只读逐证据/授权/回执验收
  report.py           # 后处理汇总、A4 验收、225 节点派生来源清单
scripts/run_e5.py      # 已冻结的分组入口，不改 E4 入口
results/E5/
  00_protocol/freeze_20261023_01/   # 第一版；含原生来源试验配置
  00_protocol/freeze_20261023_02/   # 绑定空炉头配置修订；当前基础版本
  00_protocol/receipt_20261023_01/  # A4 单独预注册
  source/native_20261023_01/        # 128 来源组记录
  source/receipt_native_20261023_01/# 16 回执初态、两种授权结果
  binding/native_20261023_01/       # 保留的未完成运行
  binding/native_20261023_02/       # 最终 9 物理控制 / 54 决策
  01_validation/native_20261023_01.json
  02_summary/phase1_20261023/        # 当前总汇总、来源图列表、成本和阶段判断
```

使用原环境 `/home/yyn/.conda/envs/ai2thor-eval/bin/python`。复用 E4 原生 headless/FIFO 启动与执行辅助函数，不需要新增模型、移动环境或 Xvfb。输出必须是新路径；以下 `reproduce_*` 不能与已有目录重名。

```bash
cd /home/yyn/embodied

# 只读核查当前正式数据，并写新的分析目录；不启动 Unity/API
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B -m e5_validation.report \
  --out results/E5/02_summary/reproduce_01

# 新原生实验前的冻结/路径检查，不创建结果目录
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/run_e5.py source \
  --mode native --dry-run --out results/E5/source/reproduce_01

# E5-A，真实 Unity 场景准备与 Pass；不执行候选动作，不调用模型
timeout 240s /home/yyn/.conda/envs/ai2thor-eval/bin/python -u -B scripts/run_e5.py source \
  --mode native --out results/E5/source/reproduce_01

# E5-E，真实目标/相邻/双空控制
timeout 240s /home/yyn/.conda/envs/ai2thor-eval/bin/python -u -B scripts/run_e5.py binding \
  --out results/E5/binding/reproduce_01

# 对这两个新运行做只读验收
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B scripts/run_e5.py verify \
  --source results/E5/source/reproduce_01 --binding results/E5/binding/reproduce_01 \
  --out results/E5/01_validation/reproduce_01.json

# 回执子实验：使用已有单独冻结的协议，不重复 --preregister
timeout 240s /home/yyn/.conda/envs/ai2thor-eval/bin/python -u -B -m e5_validation.receipt \
  --out results/E5/source/receipt_reproduce_01

# 离线测试
/home/yyn/.conda/envs/ai2thor-eval/bin/python -B -m unittest discover \
  -s tests -p 'test_e5_*.py' -v
```

`source --mode archive` 不启动 Unity，仅重用已冻结物理状态；A5/A6-budget1 将记录为 N/A，绝不把归档私有真值冒称新鲜查询。正式本轮使用的是 native 模式。

`report.py` 固定审计本轮正式目录；重新生成报告只产生相同正式数据的派生汇总，不会自动改用 `reproduce_*`。`verify` 可以检查新来源/绑定运行。回执重跑仍有原始 JSON/回执和哈希，当前总报告不会自动切换到新回执目录。

## 6. 证据、计时与下一步边界

每轮保留独立的私有真值、被测输入、字段 diff、固定候选、原始/最终授权、原生查询回执、输入哈希与来源祖先。派生 `evidence_manifest.jsonl` 共 225 个节点，区分来源可追踪、在 T0 下未被污染、以及是否足以支持当前政策。接收/采集时间为 Python Adapter 单调钟语义；历史和未记录的原生传感器时间为 null，不捏造 sensor 时间或有效区间。

原有 E4 代码、结果和文档继续只读。E5 第一轮已经给出来源/目标/简单防御的机制证据；不等于 E5 视觉、动态时间与真实部署问题全部完成。

当前应收缩到清楚的信任边界：在这个可调用原生查询、回执不可由 T0 Adapter 修改的环境里，简单可信核验已覆盖全部有效探针，按需查询还降低了调用次数。**现有结果不支持立即增加复杂融合模型。** 后续优先确认受保护来源/回执连续性在目标系统中的真实可得性；RGB/ROI 或 B/C/D 只在出现具体、自然的证据覆盖缺口时再单独冻结和执行，不靠人为造缺口延长实验。
