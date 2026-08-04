# 批量论文全文精读任务

读取 `RADAR_AGENT.md`、`data/items.json`、`data/explanations.json`、
`scripts/pending_explanations.py` 和已有高质量 `review_status=editorial` 样例。

## 本批目标

从 `review_status=abstract_backfill` 的论文中选择最多12篇进行全文精读：

1. 优先级依次为：与StreamingModelHarness直接相关、score高、日期新。
2. 识别相同arXiv编号或同标题的镜像/重复条目；一次研究后同步升级所有重复ID，
   不重复消耗检索时间。
3. 逐篇读取论文正文、作者项目页、官方代码仓库和模型页。
4. 将 `data/explanations.json` 对应记录升级为完整现有schema：
   - `review_status` 必须为 `editorial`
   - 确实读取正文后才写 `source_depth=fulltext`
   - 清楚区分论文事实和面向StreamingModelHarness的编辑判断
   - 完整填写方法、结果、项目帮助、边界、代码与模型开放状态
5. 同步改善 `data/items.json` 中对应的 `summary_zh`，但不要改原始标题、URL和分数。

## 质量约束

- 指标只能来自论文正文；无法核验的数字、许可证、代码或模型状态写未知。
- “有GitHub链接”不等于代码完整可复现；分别核验代码、权重、数据和许可证。
- 不得把摘要改写冒充全文精读。
- 禁止调用Kimi/Moonshot，禁止执行陌生论文仓库代码。
- 不修改报告、自动化脚本或其他仓库。
- 如果某篇正文确实不可访问，保留 `abstract_backfill` 并换下一篇。

完成后运行：

```text
python scripts/test_explanations.py
python scripts/build_site.py
git diff --check
```

不要提交，不要推送。最后列出升级的论文ID、重复项、失败项、测试结果和剩余数量。
最终一行必须原样输出 `DEEP_REVIEW_COMPLETE`。
