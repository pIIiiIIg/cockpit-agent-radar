# cockpit-agent-radar

全双工 · 多模态 · 座舱语音 agent 技术雷达。自动盯 arXiv / GitHub / HuggingFace /
HackerNews 上与**全双工语音、流式多模态模型、agent harness、座舱助手**相关的新东西。

**站点**: <https://piiiiiig.github.io/cockpit-agent-radar/> ·
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

## 本地跑

```bash
python scripts/fetch_rank.py    # 抓取入库 data/items.json（零第三方依赖）
python scripts/build_site.py    # 生成 docs/
python -m http.server 8099 --directory docs
```

## Research Outputs / 论文与公众号

`data/research_outputs.json` 只接收公开安全的研究状态，站点页面位于
`docs/research-outputs/`。同步脚本会移除尚未申请或未获人工批准的论文/公众号链接，并拒绝
本地路径、密钥、主机凭据和 `private_ip` 内容。专利交底书、权利要求、未公开附图和核心
实施参数不得进入本仓库或 Pages。

自动顺序是“实验归档 → 私密专利草稿 → 人工 IP 审核/申请 → 论文与公众号人工审核 →
公开安全同步”。只有 `patent_filed=true`、`human_approved=true` 和
`public_release_allowed=true` 同时成立，页面才展示稿件链接。脚本不会自动投稿、发布
公众号或向专利局提交。

## 打分怎么调

`fetch_rank.py` 顶部 `KW` 三层关键词（3=项目核心 / 2=强相关 / 1=泛背景），
命中标题权重翻倍；`THRESH` 是各源入库门槛。觉得某类内容太多/太少就动这两处。
