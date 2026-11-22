# #8 GuardAgent

编号严格对应 `share-pool/baseline.csv` 总览第 #8 项。论文：[原文](https://proceedings.mlr.press/v267/xiang25a.html)。实现标签：`ADAPTED_SOFTWARE_AGENT_EMBODIED_NA`。

## 当前环境

`~/.conda/envs/guardagent-eval/bin/python`（Python 3.10.22、pyautogen 0.2.0、OpenAI 1.7.2、HTTPX 0.27.2、NumPy 1.24.3）。HTTPX 0.28 会使旧 SDK 构造因 proxies 参数失败；不要与其他 baseline 共用升级。生成代码执行依赖 bubblewrap，原沙箱设计保留。

实际依赖快照与导入结果见 [环境审计](../../organization_audit/environments/)。Conda/venv 留在原位置，启动器按绝对 Python 路径运行，无需先 activate。`manifest.json` 记录默认环境、脚本例外和证据路径。

## 启动

在项目根目录执行（`run.sh` 也可用绝对路径从其他目录调用）：

```bash
bash e3_baseline/b8_guardagent/run.sh --check
bash e3_baseline/b8_guardagent/run.sh --list
# 已有数据上的最小离线复核；产物写进打印出的新 /tmp/embodied-run-*/workspace
bash e3_baseline/b8_guardagent/run.sh --script e3_guardagent_e2d_offline_compat.py
```

真实 API 最小入口：`--script e3_guardagent_e3a_nonthinking.py`，需 `DEEPSEEK_API_KEY`；完整具身补充回放 `e3_guardagent_e3j3_shared_pair.py` 会调用原 bwrap 执行器。整理验证仅跑离线兼容检查，不执行模型新生成代码。

仿真脚本统一把命令前缀改成 `xvfb-run -a env LIBGL_ALWAYS_SOFTWARE=1 bash .../run.sh ...`。可添加 `--work-dir /tmp/my-unique-run` 指定一个尚不存在的目录。启动器复制历史结果作输入；`--fresh-result` **只清除新工作区中指定的结果副本**，用于绕过原脚本防覆盖或 resume；原 `results/` 保留。脚本参数放在 `--` 之后。模型重跑会产生新的 API/CPU 耗时，不能当作历史结果重现保证。

## 代码与证据

E2D 兼容 → E3A 分解/B 代码/C 静态 → D/E 执行接口 → F/G 官方规则 → I 工具协议桥 → J0–J3 自建具身机制。`guardagent_deepseek_adapter/` 与官方 `external/guardagent/` 独立保留。

完整入口和旧→新路径见 [SCRIPTS.md](SCRIPTS.md)。`results` 是原始证据的相对软链接；`upstream/`（如存在）指向共享仓库/模型，未复制或改动上游源码。历史构建/补丁脚本继续归档，日常运行直接使用已生成的入口。

核心记录：

- [e2d_offline_compat.json](../../results/E3/08_guardagent/e2d_offline_compat.json)
- [e3j3_shared_pair.json](../../results/E3/08_guardagent/e3j3_shared_pair.json)

## 简短评估

软件 Agent 组件 + DeepSeek 适配；具身核心比较 N/A。SeeAct 许可 True→ALLOW、False→DENY 各1/1。研究者新建厨房策略/状态接口与 Planner 代理，C0–C4 中 C2/C3 Monitor 都 ALLOW，只有 C3 WOULD_SUBMIT；没有物理执行。这说明错误事实依赖，不构成官方具身漏洞。
