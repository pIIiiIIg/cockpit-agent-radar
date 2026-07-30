# 增强通道规程（给定时运行的 Claude 会话看）

定时抓取（GitHub Actions，见 `.github/workflows/update.yml`）是**纯启发式**的：
关键词打分、英文摘要截取，不依赖任何 LLM。本文件定义的是叠在其上的**增强通道**
——一个定时的 Claude 会话按下面规程把语义级工作补上。两层解耦：增强挂了，
站点照常更新，只是没有中文摘要和演示。

## 每次运行做三件事

先 `git pull`。所有改动最后一并 commit + push（提交信息前缀 `enhance:`）。

### 1. 补中文摘要

`data/items.json` 里 `found` 在最近 3 天内且 `summary_zh` 为空的条目：

- 写 2~3 句中文摘要。**不是翻译**——第一句说这东西是什么，第二句说
  **它与全双工/流式/多模态/座舱语音助手 harness 的关系**（这是本站存在的理由，
  与项目无关的条目直说"与本站主题相关性有限，胜在 XXX"）。
- 顺手校对 `summary_en`：截断得莫名其妙的补完整，纯营销话术压缩成信息句。
- 一次最多处理 30 条，按 score 从高到低。

### 2. 生成交互演示（每次 ≤2 个，宁缺毋滥）

从 score ≥ 10 且 `demo` 为空的新条目里挑**概念可演示**的（一种新的流式注意力、
一个判停策略、一种双工调度……）。不可演示的（纯 benchmark、模型发布公告）跳过。

- 写单文件 `docs/demos/<id>.html`：自包含（无 CDN、无外链）、深浅色自适应、
  中英文案跟随 `localStorage.getItem("radar-lang")`。
- 形式参考 `docs/demos/full-duplex-primer.html`：可拖 / 可点 / 有时间轴动画，
  让人 30 秒内抓住机制，而不是把论文图截过来。
- 写回条目的 `demo` 字段：`demos/<id>.html`。

### 3. 重建站点

```bash
python scripts/build_site.py
```

## 红线

- **绝不改** `scripts/` 与 workflow —— 增强通道只写 `data/items.json` 与 `docs/demos/`。
- 演示页禁止外部请求（Pages 上无后端，断网也要能开）。
- 拿不准的条目宁可不写 `summary_zh`，别编造论文没说的东西。
- push 前 `git pull --rebase`，Actions 可能刚提交过。
