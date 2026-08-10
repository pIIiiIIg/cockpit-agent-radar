# 每日问题驱动调研任务

在当前 `cockpit-agent-radar` 仓库生成今天的两份报告。事实输入以运行器提供的
deterministic fact skeleton 为准，并严格读取：

- `REPORT_FORMAT.md`
- `project_status/StreamingModelHarness.md`
- `reports/` 中最近一份详细报告和精简日报

不得扫描 `docs/`、`docs/items/` 或完整历史数据；输入无变化由运行器直接复用缓存，
不会启动 Agent。

## 目标

报告以 StreamingModelHarness 的真实问题和最新实验为主线，而不是论文资讯列表。

1. 从项目状态快照提取最新提交、指标、负面结果、瓶颈和待验证假设。
2. 从 Radar 新增内容中找能解决这些问题的论文、模型或开源项目。
3. 对每个候选只使用论文正文、作者项目页、官方仓库和模型页核验。
4. 明确区分：
   - 项目已经实测的事实；
   - 论文明确报告的事实；
   - 面向项目的编辑判断与待验证假设。
5. 识别同一工作的不同标题、版本和镜像，避免重复。

## 输出

生成：

- `reports/全双工语音技术增量调研-YYYY-MM-DD.md`
- `reports/每日调研日报-YYYY-MM-DD.md`
- `data/handoff/candidates/YYYY-MM-DD.json`

详细报告必须严格遵循 `REPORT_FORMAT.md`，尤其包含：

- `StreamingModelHarness 当前进展与问题`
- 问题、项目证据、相关技术、实验、成功门槛表
- P0/P1/P2
- 每篇统一的“它是什么/核心方法/论文结果/项目帮助/局限与开放状态”
- 今日建议路线和风险提醒

精简日报使用：

```text
方向：技术名（当前项目问题；技术怎么解决；准备怎样实验）
```

候选 JSON 必须逐条包含：公开论文/报告 URL、问题 bucket、可证伪假设、单变量、预计修复数、
时延预算、风险、依赖、离线门、H20 门、research value 和 public-safe patent value。
没有清晰单变量或可测指标的建议只留在报告，不进入候选。冻结 414 canary 零退化且预计净修
达到动态 full gap（当前 434/452 到 448/452，即 14）之前不得直接请求 full H20；小收益
先进入 smoke/quick/targeted 与 composition queue。+1/+4 且零退化仍是有效
component_candidate/conditional 证据，负收益记录为 negative evidence。组合前必须做
interaction/zero-regression，不能把局部数字相加。已运行/已拒绝的
candidate fingerprint 或 candidate/commit 不得重复。

## 边界

- 禁止调用 Kimi/Moonshot。
- 禁止运行陌生论文仓库代码。
- 禁止修改 `StreamingModelHarness`。
- 禁止把 candidate-ID/CMTF 已有负结果重新包装成“强制 ID 覆盖”。
- 参数化本体、云监督、SoulX 等独立实验只消费 result manifest，不重复启动。
- 只允许修改当前仓库的 `reports/`、`project_status/` 和由
  `scripts/build_site.py` 生成的 `docs/`。
- 没有证据的数字、开源状态和许可证写“未知”。

完成后运行：

```text
python scripts/test_explanations.py
python scripts/build_site.py
git diff --check
```

不要提交，不要推送。最后输出本次使用的项目问题、新增候选和测试结果。
最终一行必须原样输出 `REPORT_TASK_COMPLETE`。
