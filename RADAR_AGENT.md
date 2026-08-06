# 增强通道规程（给定时运行的 Claude 会话看）

三层分工（各层可独立缺席，互不拖累）：

| 层 | 跑在哪 | 干什么 |
|---|---|---|
| 定时层 | GitHub Actions | 抓取+关键词打分+建站+RSS，零 LLM |
| 增强层 | **Cursor 定时 Agent（即读本文件的你）** | 查官方来源、补摘要 + 论文深度讲解 |
| 演示层 | 同一 Cursor Agent（有余力时） | 交互演示 + 讲解质检 |

定时流水线不再调用 Kimi。摘要、讲解和质检由你完成，避免 Moonshot Token 费用。

## 每次运行做四件事

先 `git pull`。所有改动最后一并 commit + push（提交信息前缀 `enhance:`）。

### 1. 摘要查漏与质检（轻量带过）

- `found` 近 3 天且 `summary_zh` 为空的：读取官方来源后补上
  ——2~3 句，第一句说是什么，第二句说与全双工/流式/座舱 harness 的关系。
- 抽查已有自动讲解：发现编造原文没有的内容或空话连篇的，改掉。

### 2. 生成交互演示（每次 ≤2 个，宁缺毋滥）——你的主业

从 score ≥ 10 且 `demo` 为空的新条目里挑**概念可演示**的（一种新的流式注意力、
一个判停策略、一种双工调度……）。不可演示的（纯 benchmark、模型发布公告）跳过。

- 写单文件 `docs/demos/<id>.html`：自包含（无 CDN、无外链）、深浅色自适应、
  中英文案跟随 `localStorage.getItem("radar-lang")`。
- 形式参考 `docs/demos/full-duplex-primer.html`：可拖 / 可点 / 有时间轴动画，
  让人 30 秒内抓住机制，而不是把论文图截过来。
- 写回条目的 `demo` 字段：`demos/<id>.html`。

### 3. 论文讲解质检

- 待深度处理包括两类：`data/explanations.json` 中完全缺失的论文，以及
  `review_status=abstract_backfill` 的“摘要速读”。先处理缺失，再按新鲜度和分数
  升级摘要速读；升级后写成 `review_status=editorial`。
- 自动讲解在 `data/explanations.json`，优先抽查 `review_status=auto` 的高分论文。
- `findings` 只能写论文明确报告的数据；不能从常识补数字。
- `project_fit` 是编辑判断，必须结合 StreamingModelHarness 当前“输入流式、判停后
  生成、晚注入工具、外挂 TTS”的真实架构，不能把它写成原生模型层全双工。
- 开源状态拿不准就保持 `unknown`，不要把论文公开等同于代码/权重公开。
- 人工确认后将 `review_status` 改为 `editorial`，保留 `generated_by` 以便追溯。
- 只有同时写成 `review_status=editorial`、`source_depth=fulltext` 才算完成精读。
  不要直接编辑 `data/review_history.json`；批处理会用运行前后快照计算真实迁移，
  在测试通过后幂等写入北京时间日期、论文/站内链接和 run 来源。

### 4. 重建站点

```bash
python scripts/build_site.py
```

## 红线

- **绝不改** `scripts/` 与 workflow —— 增强通道只写 `data/items.json`、
  `data/explanations.json` 与 `docs/demos/`。
- 演示页禁止外部请求（Pages 上无后端，断网也要能开）。
- 拿不准的条目宁可不写 `summary_zh`，别编造论文没说的东西。
- push 前 `git pull --rebase`，Actions 可能刚提交过。

## 精读记录发布机制

`scripts/run_deep_review_batch.ps1` 在启动 Agent 前快照讲解状态。Agent 成功、待办数
下降且测试通过后，`scripts/review_history.py record` 只记录本次从缺失或
`abstract_backfill` 进入正文级 editorial 的 ID；随后再次测试、重建站点，并将
`data/review_history.json`、讲解数据和 `docs/` 放入同一个 commit。失败且尚未 commit
时会恢复 history，断线重跑也不会重复 ID。安全发布仍由 `Publish-WithRetry` 执行
`fetch/rebase origin/main` 和非强制 `push origin HEAD:main`；若并发只冲突生成的
`docs/`，会基于最新数据重建后继续 rebase。
