# #6 SELP

编号严格对应 `share-pool/baseline.csv` 总览第 #6 项。论文：[原文](https://arxiv.org/abs/2409.19471)。实现标签：`ORIGINAL_COMPONENT_AND_MECHANISM`。

## 当前环境

`~/.conda/envs/selp-ltl/bin/python`（Python 3.10.22、Spot 2.16）。Spot 来自 conda-forge；不要安装 PyPI 同名 spot 替代。

实际依赖快照与导入结果见 [环境审计](../../organization_audit/environments/)。Conda/venv 留在原位置，启动器按绝对 Python 路径运行，无需先 activate。`manifest.json` 记录默认环境、脚本例外和证据路径。

## 启动

在项目根目录执行（`run.sh` 也可用绝对路径从其他目录调用）：

```bash
bash e3_baseline/b6_selp/run.sh --check
bash e3_baseline/b6_selp/run.sh --list
# 已有数据上的最小离线复核；产物写进打印出的新 /tmp/embodied-run-*/workspace
bash e3_baseline/b6_selp/run.sh --script e3_selp_e4_constrained_decoding.py --fresh-result E3/selp/e4_constrained_decoding.json
```

官方完整生成入口仍缺资源。现有组件可用，无需为整理工作重新下载或自造缺失的模型、Prompt、数据。

仿真脚本统一把命令前缀改成 `xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 bash .../run.sh ...`。可添加 `--work-dir /tmp/my-unique-run` 指定一个尚不存在的目录。启动器复制历史结果作输入；`--fresh-result` **只清除新工作区中指定的结果副本**，用于绕过原脚本防覆盖或 resume；原 `results/` 保留。脚本参数放在 `--` 之后。模型重跑会产生新的 API/CPU 耗时，不能当作历史结果重现保证。

## 代码与证据

E1 官方 LTL smoke → E2 合成观察 → E3B 历史良性场景 → E3C 危险授权 → E4 合成 tokenizer 的 constrained decoding 核心。后者不能替代原微调模型生成。

完整入口和旧→新路径见 [SCRIPTS.md](SCRIPTS.md)。`results` 是原始证据的相对软链接；`upstream/`（如存在）指向共享仓库/模型，未复制或改动上游源码。历史构建/补丁脚本继续归档，日常运行直接使用已生成的入口。

核心记录：

- [e1_official_ltl_smoke.json](../../results/E3/selp/e1_official_ltl_smoke.json)
- [e3c_unsafe_authorization.json](../../results/E3/selp/e3c_unsafe_authorization.json)
- [e4_constrained_decoding.json](../../results/E3/selp/e4_constrained_decoding.json)

## 简短评估

O 符号组件 + M 语义映射。官方 LTL/Spot、等价投票和受约束解码核心已运行；厨房实验复用 b2 的4个物理场景 metadata，非独立新采集。空炉污染误授1/1、良性污染误拒3/3。缺原任务数据、四份 Prompt 和微调权重，NL→LTL→规划完整流程仍未重现；不是原生 runtime monitor。
