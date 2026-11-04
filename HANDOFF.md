# HANDOFF — 下一轮工作指引（给 hong-tm 和他的 AI）

> 上游维护者：lewyk510。上一轮成果已全部合并（资料刷新 + 107 测试 + 评测执行器 run_evals.py）。
> 干活规矩：先读 `SKILL.md` 和 `references/70-craft-gate-and-spec.md`（工艺门槛）→ 建分支 `handoff-return/<日期>` → 小步提交 → 收工写 `HANDOFF-RETURN.md` 并推回分支 → 开 PR。

## 当前状态

- run_evals.py 能对 evals/evals.json 里机器可查的成功标准打分；19 个行为用例仍是 spec-only
- selftest 16 项、单测 107 个、freshness 24/24 全绿

## 下一轮任务（按优先级）

1. **评测扩容**：把 evals.json 里机器可查的成功标准占比提高——逐条审阅 19 个用例，能拆出可执行判据的拆出来（结构、韵脚、字数、意象命中），让 run_evals.py 的覆盖从「机器可查子集」扩大。
2. **lyric_lint 增强**：跑一遍最近的真实歌词样本找漏报的 AI 味模式，把新模式加进 lint 规则并配正反测试（现有规则都是 mutation-proven 的，保持这个标准）。
3. **资料保鲜**：references/10-13（Suno 机制）距上次人工核对已过一轮，跑 `check_freshness.py`，对 warning/stale 条目重新对照官方文档，改动的条目更新 freshness.json 日期。

## 红线

- 不降低 LYR-LINT 的门槛来让样本通过；标准是标准
- 引用外部事实必须带来源，dead link 直接替换或删除
