# cockpit-agent-radar

全双工 · 多模态 · 座舱语音 agent 技术雷达。自动盯 arXiv / GitHub / HuggingFace /
HackerNews 上与**全双工语音、流式多模态模型、agent harness、座舱助手**相关的新东西。

**站点**: <https://piiiiiig.github.io/cockpit-agent-radar/> ·
**精读记录**: [Reviews](https://piiiiiig.github.io/cockpit-agent-radar/reviews.html) ·
**自动化系统讲解**: [Automation](https://piiiiiig.github.io/cockpit-agent-radar/automation/) ·
**高收益组件**: [Solutions](https://piiiiiig.github.io/cockpit-agent-radar/solutions/) ·
**订阅**: [RSS](https://piiiiiig.github.io/cockpit-agent-radar/feed.xml)

## Radar → Harness 证据交接

`data/handoff/ledger.json` 按研究日期保存可公开的恢复点。每个定时任务先调用
`scripts/handoff_ledger.py next` 找出最早缺失日期，因此漏跑日优先于“今天”。每阶段记录
输入/输出 commit、产物、状态、重试和下一阶段，终态写入幂等。

Radar 只有在全文证据和两份报告都存在后才发布
`data/handoff/manifests/YYYY-MM-DD.json`。Harness ack 结构化候选，先离线回放，再决定是否
向动态 H20 池排队，并返回 result manifest；Radar 下一班把正/负结果回写 Solutions/Reports。
Solutions 使用双层展示：第一层只列正式保留/高收益组件；第二层每日实验工作台记录 proposed、
offline compared、conditional、H20 tested、rejected 与 invalid/blocked。即使当天新增高收益为
0，也显示实验活动、失败结论和节省的 GPU 成本，绝不把候选冒充好方案。
`data/experiment_activity.json` 是每日工作台事实源；candidate ledger 某日已有发布事件而该日
没有 activity 时，建站必须失败。没有候选时写 `research_exhausted` 和精读/筛选数量。
`check-stale` 在任何必需事件超过 24 小时无终态时非零退出。

补精读不伪造历史时间：`review_date/reviewed_at` 保留实际执行时间，
`origin.catchup_for` 只记录所补调度日期。公开 manifest 禁止密钥、私网 IP 和私有路径。
publication/patent 对接只公开贡献标签，申请前不公开独立分支的实现细节。

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

## 自动化系统讲解页面

`scripts/build_automation.py` 是 `/automation/` 总览、六个环节子页和 Hybrid C
完整案例页的可维护源码；`scripts/build_site.py` 每次建站都会重新生成
`docs/automation/`。页面沿用站点双语、深浅主题和无外部依赖设计，并提供可暂停、
可重置且尊重 `prefers-reduced-motion` 的流程动画。

论文调研节点是**混合流程**：确定性脚本负责四源抓取、去重、评分和摘要回填，
Cursor 负责筛选后的正文精读；不能把整条调研链标成“纯脚本”。Research 和 Reports
讲解页在构建时安全读取 `data/items.json`、`data/explanations.json`、
`data/review_history.json` 与 `reports/`，动态展示收录、论文、摘要速读、正文精读、
精读日期及日报统计，并链接到实际的 Reviews、day、论文详情、原论文和公开日报。
缺失或损坏的数据文件会降级显示，不会阻断页面生成；所有动态文本都会 HTML 转义。
事实状态日期和构建时间同样由每次构建生成，不在源码中固定。

第七节点 `/automation/limitations/` 是双语证据审计页，明确 A/B/Hybrid C 的可比
范围、论文到候选的来源链、评测/指标盲区和允许声明 99% 的条件。`selection/` 则按
当前 evolution 评分与 registry 源码区分 `research_eligible` /
`production_eligible`，展示可键盘展开的决策树、五类实验状态、Pareto/组件留存规则、
真实 registry 链接和当前三组分范围判定。两页都把 partial、冒烟和错误桶证据与
qualified/production 明确分开。

所有 automation 子页的主要步骤、卡片和案例时间轴都保留短摘要，并附原生
`details/summary` 双语详细层，说明输入、运行、产物、失败与证据边界。每页提供
展开/收起全部控制、键盘焦点与 hash 定位；打印时默认展示详细内容，移动端和
`prefers-reduced-motion` 也受测试保护。严格 B 审计另区分 B pure（无 SoulX）、
B+真实 SoulX 与 audio-derived C，并把 369/452 幂等合并口径、音频 provenance、
标签敏感性、CarSim/最终态和时延边界写入 Research、Selection 与 Limitations。

## 高收益组件同步与页面

`scripts/sync_harness_solutions.py` 从指定的 StreamingModelHarness clone/ref 通过
`git show` 只读提取版本化 `retained_components.json`、实验 registry 和公开摘要字段，
写入站点自己的 `data/harness_solutions.json`。同步严格筛选 `retained`，或具有正向
指标、样本范围且安全未退化的 `conditional/partial_improvement`；组合指标保留
`combination_only` 标记，不分摊给单组件。`rejected/invalid` 只进入负结果区。

同步器只保留 allowlist 字段并脱敏 host、key、本机路径；源不可用时保留上次快照并
标记 `stale`，不会清空方案。Windows 日报/精读发布脚本会在建站前同步并把快照与
`docs/` 同 commit；GitHub Actions 无私有 Harness 访问时直接使用已提交快照。

```bash
python scripts/sync_harness_solutions.py \
  --source ../StreamingModelHarness \
  --branch automation/agent-h20-loop
python scripts/test_solutions.py
python scripts/build_site.py
```

建站生成 `/solutions/`、按北京时间归档的每日变化页以及每组件详情页；首页和日报把
实验反馈作为独立区块展示，不与论文资讯混写。

修改后运行：

```bash
python scripts/test_explanations.py
python scripts/test_automation_pages.py
python scripts/test_solutions.py
python scripts/build_site.py
git diff --check
```

自动化讲解页是普通 Pages 路由，不加入 RSS 条目。云端 Pages smoke 会验收总览、
调研、日报、选择、局限审计、H20 和 Hybrid C 案例路由；Research 测试还会核对动态计数与
`review_history.json`、真实详情/日报文件、缺数据降级、HTML 转义和页面互链。

## 打分怎么调

`fetch_rank.py` 顶部 `KW` 三层关键词（3=项目核心 / 2=强相关 / 1=泛背景），
命中标题权重翻倍；`THRESH` 是各源入库门槛。觉得某类内容太多/太少就动这两处。
