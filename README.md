# cockpit-agent-radar

全双工 · 多模态 · 座舱语音 agent 技术雷达。自动盯 arXiv / GitHub / HuggingFace /
HackerNews 上与**全双工语音、流式多模态模型、agent harness、座舱助手**相关的新东西。

**站点**: <https://piiiiiig.github.io/cockpit-agent-radar/> ·
**订阅**: [RSS](https://piiiiiig.github.io/cockpit-agent-radar/feed.xml)

## 架构：两层解耦

```
┌ 定时层(GitHub Actions, 北京 9:00/14:00/19:00) ── 永不依赖 LLM ┐
│  scripts/fetch_rank.py   四源抓取 + 关键词打分 + 去重入库      │
│  scripts/build_site.py   生成 docs/(首页/子页/存档/RSS,双语)   │
└──────────────────────── commit & push ───────────────────────┘
┌ 增强层(定时 Claude 会话, 规程见 RADAR_AGENT.md) ── 可缺席 ────┐
│  为新条目写中文摘要(不是翻译,重点是与座舱 harness 的关系)      │
│  为高分新技术生成自包含交互演示页 docs/demos/<id>.html        │
└───────────────────────────────────────────────────────────────┘
```

定时层挂了增强层无事可做；增强层挂了站点照常更新——只是暂时没有中文摘要和演示。

## 本地跑

```bash
python scripts/fetch_rank.py    # 抓取入库 data/items.json（零第三方依赖）
python scripts/build_site.py    # 生成 docs/
python -m http.server 8099 --directory docs
```

## 打分怎么调

`fetch_rank.py` 顶部 `KW` 三层关键词（3=项目核心 / 2=强相关 / 1=泛背景），
命中标题权重翻倍；`THRESH` 是各源入库门槛。觉得某类内容太多/太少就动这两处。
