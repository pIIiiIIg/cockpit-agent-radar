# cockpit-agent-radar

全双工 · 多模态 · 座舱语音 agent 技术雷达。自动盯 arXiv / GitHub / HuggingFace /
HackerNews 上与**全双工语音、流式多模态模型、agent harness、座舱助手**相关的新东西。

**站点**: <https://piiiiiig.github.io/cockpit-agent-radar/> ·
**精读记录**: [Reviews](https://piiiiiig.github.io/cockpit-agent-radar/reviews.html) ·
**订阅**: [RSS](https://piiiiiig.github.io/cockpit-agent-radar/feed.xml)

## 架构：两层解耦

```
┌ 定时层(GitHub Actions, 北京 9:00/14:00/19:00) ── 永不依赖 LLM ┐
│  scripts/fetch_rank.py   四源抓取 + 关键词打分 + 去重入库      │
│  scripts/build_site.py   生成 docs/(首页/论文讲解/存档/RSS)   │
└──────────────────────── commit & push ───────────────────────┘
┌ 增强层(Cursor 定时 Agent, 规程见 RADAR_AGENT.md) ─ 可缺席 ───┐
│  抓取后读取官方来源，写中文摘要与结构化深度讲解；不调用 Kimi     │
│  为高分新技术生成自包含交互演示页 docs/demos/<id>.html        │
└───────────────────────────────────────────────────────────────┘
```

定时层挂了增强层无事可做；增强层挂了站点照常更新——论文页会显示“深度讲解
正在排队”，有 key 后按相关度持续回填。

## 论文深度讲解

每篇论文详情页支持以下结构：

- 一句话说明、问题与核心方法
- 分步工作机制和论文明确报告的结果
- 对 StreamingModelHarness 的帮助（明确标为编辑判断）
- 局限、代码与模型开放情况

人工复核内容和自动生成内容统一存放在 `data/explanations.json`。Cursor 定时 Agent
优先处理新论文，再按相关度逐班回填历史论文；Agent 缺席不影响 GitHub Actions 的
抓取、建站和 RSS。`scripts/enhance_kimi.py` 仅保留为手动备用，不在定时流水线运行。

为避免新论文在两班之间只显示“排队中”，GitHub Actions 会先运行
`backfill_abstract_explanations.py` 生成明确标注的“摘要速读”（零 API、无模型费用）；
Cursor Agent 随后读取正文，将 `review_status=abstract_backfill` 的条目升级为深度讲解。

正文精读历史单独存放在 `data/review_history.json`。它只接受
`review_status=editorial` 且 `source_depth=fulltext` 的状态迁移，并按北京时间记录
论文来源、站内详情和自动化 run；摘要回填不会计数。`run_deep_review_batch.ps1`
在 Agent 前保存状态快照，测试通过后才计算本批实际升级，和数据及 `docs/` 放在同一
commit 中发布。ID 去重保证断线重试幂等，同题镜像通过 `canonical_id/mirror_of`
明确标识并在网页合并展示。历史数据若只能由 `generated_at` 核验，会标为
`backfilled=true`，不会猜测旧批次。

## 本地跑

```bash
python scripts/fetch_rank.py    # 抓取入库 data/items.json（零第三方依赖）
python scripts/build_site.py    # 生成 docs/
python -m http.server 8099 --directory docs
```

## 打分怎么调

`fetch_rank.py` 顶部 `KW` 三层关键词（3=项目核心 / 2=强相关 / 1=泛背景），
命中标题权重翻倍；`THRESH` 是各源入库门槛。觉得某类内容太多/太少就动这两处。
