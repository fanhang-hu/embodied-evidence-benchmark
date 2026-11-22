# 实验脚本索引

文件名保留的编号用于追溯旧日志；此表给出归属和旧入口。构建/补丁/下载脚本是历史工程步骤，不是新的实验结果。

| 当前入口 | 原入口 | 文件头说明 |
|---|---|---|
| [a_oracle_pre_execution_guard.py](a_oracle_pre_execution_guard.py) | `e2a_oracle_pre_execution_guard.py` | 按文件名的阶段/用途运行；详见 README 和源码。 |
| [b1_visual_crosscheck.py](b1_visual_crosscheck.py) | `e2b1_visual_crosscheck.py` | 按文件名的阶段/用途运行；详见 README 和源码。 |
| [b1_visual_crosscheck_fixed.py](b1_visual_crosscheck_fixed.py) | `e2b1_visual_crosscheck_fixed.py` | 按文件名的阶段/用途运行；详见 README 和源码。 |
| [b2_benign_stove_setup.py](b2_benign_stove_setup.py) | `e2b2_benign_stove_setup.py` | E2-B2A: Construct a REAL positive-control stove state in AI2-THOR. |
| [b2b_vlm_positive_control.py](b2b_vlm_positive_control.py) | `e2b2b_vlm_positive_control.py` | E2-B2B: Real-Pan RGB positive control, one DeepSeek VLM call. |
| [b2c_visual_pair_audit.py](b2c_visual_pair_audit.py) | `e2b2c_visual_pair_audit.py` | E2-B2C: Offline audit of the empty-stove vs real-pan RGB pair. |
| [b2d_roi_perception_pair.py](b2d_roi_perception_pair.py) | `e2b2d_roi_perception_pair.py` | E2-B2D: matched ROI visual readout for actual empty vs pan-on-burner scenes. |
| [b3a_wrong_burner_control.py](b3a_wrong_burner_control.py) | `e2b3a_wrong_burner_control.py` | E2-B3A: Real Pan on the WRONG burner. |
| [b3b_wrong_burner_vlm.py](b3b_wrong_burner_vlm.py) | `e2b3b_wrong_burner_vlm.py` | E2-B3B: Scene-level vision versus target-specific safety. |
| [b3c_target_specific_vlm.py](b3c_target_specific_vlm.py) | `e2b3c_target_specific_vlm.py` | E2-B3C: target-specific visual grounding on three real RGB scenes. |
| [b4_target_fusion.py](b4_target_fusion.py) | `e2b4_target_fusion.py` | E2-B4: Offline target-specific authorization fusion. |
| [b5a_temporal_evidence.py](b5a_temporal_evidence.py) | `e2b5a_temporal_evidence.py` | E2-B5A: Real pan-on-target -> pan-removed state transition. |
| [b5b_stale_visual_replay.py](b5b_stale_visual_replay.py) | `e2b5b_stale_visual_replay.py` | E2-B5B: Offline stale-visual-evidence counterfactual. |
| [b5c_visual_binding_audit.py](b5c_visual_binding_audit.py) | `e2b5c_visual_binding_audit.py` | E2-B5C: Audit target-specific visual binding disagreement. |
| [b5d_vlm_repeatability.py](b5d_vlm_repeatability.py) | `e2b5d_vlm_repeatability.py` | E2-B5D: Repeated target-specific VLM inference. |
| [b5e_repeat_consensus.py](b5e_repeat_consensus.py) | `e2b5e_repeat_consensus.py` | E2-B5E: Repeatability, voting and stale-evidence replay. |
| [b6_native_boundary_audit.py](b6_native_boundary_audit.py) | `e2b6_native_boundary_audit.py` | E2-B6: Native input boundary and attacker-access audit. |
| [b7a_native_toctou_dryrun.py](b7a_native_toctou_dryrun.py) | `e2b7a_native_toctou_dryrun.py` | E2-B7A: Native check-to-use dry-run with real state transition. |
| [b7b_native_rl_toctou.py](b7b_native_rl_toctou.py) | `e2b7b_native_rl_toctou.py` | E2-B7B: Original RL execution loop, controlled TOCTOU. |
| [b7c_native_window_timing.py](b7c_native_window_timing.py) | `e2b7c_native_window_timing.py` | E2-B7C: Native check-to-use timing under direct-action policy. |
| [b7d_microaction_timing.py](b7d_microaction_timing.py) | `e2b7d_microaction_timing.py` | E2-B7D: Check-to-use timing across native RL micro-actions. |
| [b7e_preexecution_revalidation.py](b7e_preexecution_revalidation.py) | `e2b7e_preexecution_revalidation.py` | E2-B7E: Test a simple pre-execution revalidation gate. |
| [b7f_multiagent_smoke.py](b7f_multiagent_smoke.py) | `e2b7f_multiagent_smoke.py` | E2-B7F: Two AI2-THOR agents sharing one real scene. |
| [b7g_two_agent_toctou.py](b7g_two_agent_toctou.py) | `e2b7g_two_agent_toctou.py` | E2-B7G: Two-agent shared-world TOCTOU with native RL loop. |
| [b7h_threaded_race.py](b7h_threaded_race.py) | `e2b7h_threaded_race.py` | E2-B7H: Two-agent threaded scheduling feasibility. |
| [executor_receipts.py](executor_receipts.py) | `e2_executor_receipts.py` | 按文件名的阶段/用途运行；详见 README 和源码。 |
| [full_trace.py](full_trace.py) | `e2_full_trace.py` | 按文件名的阶段/用途运行；详见 README 和源码。 |
| [history_defense.py](history_defense.py) | `e2_history_defense.py` | 按文件名的阶段/用途运行；详见 README 和源码。 |
| [history_monitor_v2.py](history_monitor_v2.py) | `e2_history_monitor_v2.py` | 按文件名的阶段/用途运行；详见 README 和源码。 |
| [history_replay.py](history_replay.py) | `e2_history_replay.py` | 按文件名的阶段/用途运行；详见 README 和源码。 |
| [matched_observation.py](matched_observation.py) | `e2_matched_observation.py` | 按文件名的阶段/用途运行；详见 README 和源码。 |
| [metric_pilot.py](metric_pilot.py) | `e2_metric_pilot.py` | 按文件名的阶段/用途运行；详见 README 和源码。 |
| [observation_audit.py](observation_audit.py) | `e2_observation_audit.py` | 按文件名的阶段/用途运行；详见 README 和源码。 |
| [stove_camera_view_probe.py](stove_camera_view_probe.py) | `m6_stove_view_probe.py` | M6-3B: locate a stove observation with ground truth only for camera selection. |
| [viewpoint_check.py](viewpoint_check.py) | `e2_viewpoint_check.py` | 按文件名的阶段/用途运行；详见 README 和源码。 |
| [vision_payload_probe.py](vision_payload_probe.py) | `m6_vision_input_probe.py` | 按文件名的阶段/用途运行；详见 README 和源码。 |
| [vlm_stove_state_readout.py](vlm_stove_state_readout.py) | `m6_vlm_visual_readout.py` | M6-3C: one-shot, image-only stove-state readout (no AI2-THOR actuation). |
| [vlm_stove_state_readout_retry.py](vlm_stove_state_readout_retry.py) | `m6_vlm_visual_readout_retry.py` | M6-3C: one-shot, image-only stove-state readout (no AI2-THOR actuation). |
