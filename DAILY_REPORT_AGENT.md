# 每日问题驱动调研任务

在当前 `cockpit-agent-radar` 仓库生成今天的两份报告。严格读取：

- `REPORT_FORMAT.md`
- `project_status/StreamingModelHarness.md`
- `data/items.json`
- `data/explanations.json`
- `reports/` 中最近一份详细报告和精简日报

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

## 边界

- 禁止调用 Kimi/Moonshot。
- 禁止运行陌生论文仓库代码。
- 禁止修改 `StreamingModelHarness`。
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
