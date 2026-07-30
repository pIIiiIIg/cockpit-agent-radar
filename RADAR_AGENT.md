# 增强通道规程（给定时运行的 Claude 会话看）

三层分工（各层可独立缺席，互不拖累）：

| 层 | 跑在哪 | 干什么 |
|---|---|---|
| 定时层 | GitHub Actions | 抓取+关键词打分+建站+RSS，零 LLM |
| 摘要层 | Actions 里调 Kimi（`scripts/enhance_kimi.py`，key 在 repo secret） | 补 `summary_zh` |
| 演示层 | **本机定时 Claude 会话（即读本文件的你）** | 交互演示 + 摘要质检 |

摘要主力已是云端 Kimi——你的活是它做不了的部分。

## 每次运行做三件事

先 `git pull`。所有改动最后一并 commit + push（提交信息前缀 `enhance:`）。

### 1. 摘要查漏与质检（轻量带过）

- Kimi 因限流漏掉的（`found` 近 3 天且 `summary_zh` 为空）：按其标准补上
  ——2~3 句，第一句说是什么，第二句说与全双工/流式/座舱 harness 的关系。
- 抽查几条 Kimi 写的：发现编造原文没有的内容或空话连篇的，改掉。

### 2. 生成交互演示（每次 ≤2 个，宁缺毋滥）——你的主业

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
