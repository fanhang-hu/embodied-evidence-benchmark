# #5 HD-Guard / HomeSafe-Bench

编号严格对应 `share-pool/baseline.csv` 总览第 #5 项。论文：[原文](https://arxiv.org/abs/2603.11975)。实现标签：`ADAPTED_AUXILIARY`。

## 当前环境

`~/.conda/envs/refinement-gap-eval/bin/python`（Python 3.11.17、OpenCV 4.10.0、Pillow 11.3.0、OpenAI 3.35.1）。官方 MiniCPM/Qwen 双 GPU 模型未装，此处为原生调度 + CPU/DeepSeek 适配。

实际依赖快照与导入结果见 [环境审计](../../organization_audit/environments/)。Conda/venv 留在原位置，启动器按绝对 Python 路径运行，无需先 activate。`manifest.json` 记录默认环境、脚本例外和证据路径。

## 启动

在项目根目录执行（`run.sh` 也可用绝对路径从其他目录调用）：

```bash
bash e3_baseline/b5_hdguard/run.sh --check
bash e3_baseline/b5_hdguard/run.sh --list
# 已有数据上的最小离线复核；产物写进打印出的新 /tmp/embodied-run-*/workspace
bash e3_baseline/b5_hdguard/run.sh --script e3_hdguard_e5e_quality_gate.py --fresh-result E3/05_hdguard/e5e_quality_gate/e5e_quality_gate_replay.json
```

真实 API 调度入口：`--script e3_hdguard_e5b_deepseek_native.py`；已有 `DEEPSEEK_API_KEY`，支持 `DEEPSEEK_BASE_URL` / `OPENAI_BASE_URL`，`HD_DEEPSEEK_MODEL` 默认且断言为 `deepseek-flash`。离线质量门命令无需任何模型或密钥。

仿真脚本统一把命令前缀改成 `xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 bash .../run.sh ...`。可添加 `--work-dir /tmp/my-unique-run` 指定一个尚不存在的目录。启动器复制历史结果作输入；`--fresh-result` **只清除新工作区中指定的结果副本**，用于绕过原脚本防覆盖或 resume；原 `results/` 保留。脚本参数放在 `--` 之后。模型重跑会产生新的 API/CPU 耗时，不能当作历史结果重现保证。

## 代码与证据

E0 数据/源码 → E1 调度桩 → E2 共享污染桩 → E3 GT 时间轴 → E4 简防 → E5A/B 真 API → E5C 重复 → E5D/D2 分支/固定 Slow → E5E 离线质量门。桩实验与真模型记录分开。

完整入口和旧→新路径见 [SCRIPTS.md](SCRIPTS.md)。`results` 是原始证据的相对软链接；`upstream/`（如存在）指向共享仓库/模型，未复制或改动上游源码。历史构建/补丁脚本继续归档，日常运行直接使用已生成的入口。

核心记录：

- [e5c_summary.json](../../results/E3/05_hdguard/e5c_repeatability/e5c_summary.json)
- [e5e_quality_gate_replay.json](../../results/E3/05_hdguard/e5e_quality_gate/e5e_quality_gate_replay.json)

## 简短评估

A 级视觉告警辅助 Pilot。E5-C 单视频 5 对 Clean 平均评分70、Mask0，严格成功1/5；固定 Slow 调用翻转3/5。E5-E 简单质量门检出14/14黑帧，Clean 0/22，2%亮度正常帧22/22被 DEFER。全黑属于证据缺失；视频事件评分不等于执行前授权/机器人止动，不计 UAR/E-ASR。当前支线已按 No-Go 阶段结项。
