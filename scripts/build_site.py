#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 data/items.json 生成静态站到 docs/（GitHub Pages 从 main:/docs 服务）。

双语方案：所有 UI 文案成对写成 <span class="l-zh">/<span class="l-en">，
CSS 按 <html data-lang> 只显示一种；切换按钮改属性并存 localStorage。
条目正文：summary_zh 缺失时中文界面回落显示英文（增强通道补翻译后自动切换）。

模板用 __TOKEN__ 替换而不用 f-string——HTML/CSS/JS 里全是花括号，f-string 是灾难。
"""
import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
BASE = "https://piiiiiig.github.io/cockpit-agent-radar"
CST = timezone(timedelta(hours=8))

KIND = {"paper": ("论文", "Paper"), "repo": ("仓库", "Repo"),
        "news": ("新闻", "News"), "model": ("模型", "Model")}


def esc(s):
    return html.escape(s or "", quote=True)


def pair(zh, en):
    return f'<span class="l-zh">{zh}</span><span class="l-en">{en}</span>'


STYLE = """
:root { --bg:#0e1116; --card:#161b23; --fg:#dbe2ea; --dim:#8b96a5;
        --acc:#4da3ff; --line:#232b36; --chip:#1d2733; }
@media (prefers-color-scheme: light) {
  :root { --bg:#f7f8fa; --card:#ffffff; --fg:#1c2430; --dim:#5d6b7c;
          --acc:#0d6ecc; --line:#e4e8ee; --chip:#eef2f7; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
       font:15px/1.65 system-ui,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }
a { color:var(--acc); text-decoration:none; } a:hover { text-decoration:underline; }
.wrap { max-width:780px; margin:0 auto; padding:20px 16px 60px; }
header.site { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap;
              border-bottom:1px solid var(--line); padding-bottom:14px; margin-bottom:6px; }
header.site h1 { font-size:20px; margin:0; }
header.site .sub { color:var(--dim); font-size:13px; }
.toolbar { margin-left:auto; display:flex; gap:8px; }
.btn { background:var(--chip); color:var(--fg); border:1px solid var(--line);
       border-radius:6px; padding:3px 10px; font-size:13px; cursor:pointer; }
.btn:hover { border-color:var(--acc); }
h2.day { font-size:14px; color:var(--dim); margin:26px 0 10px;
         border-left:3px solid var(--acc); padding-left:8px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px;
        padding:12px 14px; margin-bottom:10px; }
.card .t { font-size:15.5px; font-weight:600; }
.card .meta { color:var(--dim); font-size:12.5px; margin-top:4px;
              display:flex; gap:10px; flex-wrap:wrap; }
.badge { display:inline-block; background:var(--chip); border-radius:5px;
         padding:0 7px; font-size:12px; color:var(--dim); }
.badge.hi { color:var(--acc); }
.sum { margin-top:6px; font-size:14px; color:var(--fg); opacity:.92; }
.tags { margin-top:6px; } .tags .badge { margin-right:5px; }
.demo-link { color:#3fb46b; font-weight:600; }
[data-lang="zh"] .l-en { display:none; } [data-lang="en"] .l-zh { display:none; }
.item-page .sum-block { background:var(--card); border:1px solid var(--line);
        border-radius:10px; padding:14px 16px; margin:14px 0; }
footer { margin-top:40px; color:var(--dim); font-size:12.5px;
         border-top:1px solid var(--line); padding-top:12px; }
"""

JS = """
(function () {
  var saved = localStorage.getItem("radar-lang")
           || (navigator.language.startsWith("zh") ? "zh" : "en");
  document.documentElement.setAttribute("data-lang", saved);
  window.toggleLang = function () {
    var next = document.documentElement.getAttribute("data-lang") === "zh" ? "en" : "zh";
    document.documentElement.setAttribute("data-lang", next);
    localStorage.setItem("radar-lang", next);
  };
})();
"""

SHELL = """<!DOCTYPE html>
<html lang="zh" data-lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<link rel="alternate" type="application/rss+xml" title="cockpit-agent-radar"
      href="__BASE__/feed.xml">
<style>__STYLE__</style>
<script>__JS__</script>
</head>
<body><div class="wrap">
<header class="site">
  <h1><a href="__BASE__/" style="color:inherit">🚗 cockpit-agent-radar</a></h1>
  <span class="sub">__SUB__</span>
  <span class="toolbar">
    <button class="btn" onclick="toggleLang()">中 / EN</button>
    <a class="btn" href="__BASE__/feed.xml">RSS</a>
    <a class="btn" href="__BASE__/archive.html">__ARCHIVE_LABEL__</a>
  </span>
</header>
__BODY__
<footer>__FOOTER__</footer>
</div></body></html>
"""


def shell(title, body):
    sub = pair("全双工 · 多模态 · 座舱语音 agent 技术雷达",
               "full-duplex · multimodal · cockpit voice-agent radar")
    foot = pair(
        "每天北京时间 9:00 / 14:00 / 19:00 自动更新 · 订阅 RSS 获取推送 · "
        '源码在 <a href="https://github.com/pIIiiIIg/cockpit-agent-radar">GitHub</a>',
        "Updates 9:00 / 14:00 / 19:00 (UTC+8) daily · subscribe via RSS · "
        '<a href="https://github.com/pIIiiIIg/cockpit-agent-radar">source</a>')
    return (SHELL.replace("__TITLE__", esc(title)).replace("__BASE__", BASE)
            .replace("__STYLE__", STYLE).replace("__JS__", JS)
            .replace("__SUB__", sub).replace("__FOOTER__", foot)
            .replace("__ARCHIVE_LABEL__", pair("存档", "Archive"))
            .replace("__BODY__", body))


def card(it, link_self=True):
    zk, ek = KIND.get(it["kind"], (it["kind"], it["kind"]))
    href = f'{BASE}/items/{it["id"]}.html' if link_self else esc(it["url"])
    meta = [f'<span class="badge hi">{pair(zk, ek)}</span>',
            f'<span>{esc(it["source"])}</span>']
    if it.get("published"):
        meta.append(f'<span>{esc(it["published"])}</span>')
    if it.get("stars"):
        meta.append(f'<span>★ {it["stars"]}</span>')
    meta.append(f'<span title="relevance">◈ {it["score"]}</span>')
    if it.get("demo"):
        meta.append(f'<a class="demo-link" href="{BASE}/{esc(it["demo"])}">'
                    + pair("▶ 交互演示", "▶ live demo") + "</a>")
    zh = it.get("summary_zh") or it.get("summary_en") or ""
    en = it.get("summary_en") or ""
    summ = (f'<div class="sum"><span class="l-zh">{esc(zh[:200])}</span>'
            f'<span class="l-en">{esc(en[:200])}</span></div>')
    return (f'<div class="card"><div class="t"><a href="{href}">{esc(it["title"])}'
            f'</a></div><div class="meta">{"".join(meta)}</div>{summ}</div>')


def item_page(it):
    zk, ek = KIND.get(it["kind"], (it["kind"], it["kind"]))
    zh = it.get("summary_zh")
    zh_block = (esc(zh) if zh else
                esc(it.get("summary_en") or "") +
                ' <i style="color:var(--dim)">(中文摘要待增强通道生成)</i>')
    demo = ""
    if it.get("demo"):
        demo = (f'<p><a class="demo-link" href="{BASE}/{esc(it["demo"])}">'
                + pair("▶ 打开交互演示", "▶ open live demo") + "</a></p>")
    body = f"""
<div class="item-page">
  <h2 style="margin:18px 0 6px">{esc(it["title"])}</h2>
  <div class="meta" style="color:var(--dim);font-size:13px">
    <span class="badge hi">{pair(zk, ek)}</span> · {esc(it["source"])}
    · {esc(it.get("published") or "")} · ◈ {it["score"]}
  </div>
  <div class="sum-block"><b>{pair("摘要", "Summary")}</b><br>
    <span class="l-zh">{zh_block}</span>
    <span class="l-en">{esc(it.get("summary_en") or "")}</span></div>
  {demo}
  <p><a class="btn" href="{esc(it["url"])}">{pair("→ 原文链接", "→ original link")}</a>
     &nbsp; <a class="btn" href="{BASE}/">{pair("← 返回列表", "← back")}</a></p>
  <div class="tags">{"".join(f'<span class="badge">{esc(t)}</span>' for t in it.get("tags", []))}</div>
</div>"""
    return shell(it["title"], body)


def rss(items):
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<rss version="2.0"><channel>',
           "<title>cockpit-agent-radar</title>",
           f"<link>{BASE}/</link>",
           "<description>full-duplex / multimodal / cockpit voice-agent radar"
           "（全双工·多模态·座舱语音技术雷达）</description>"]
    for it in items[:40]:
        desc = it.get("summary_zh") or it.get("summary_en") or ""
        out += ["<item>",
                f"<title>{esc(it['title'])}</title>",
                f"<link>{BASE}/items/{it['id']}.html</link>",
                f"<guid isPermaLink=\"true\">{BASE}/items/{it['id']}.html</guid>",
                f"<description>{esc(desc[:300])}</description>",
                "</item>"]
    out += ["</channel></rss>"]
    return "\n".join(out)


def main():
    data = json.load(open(os.path.join(ROOT, "data", "items.json"), encoding="utf-8"))
    items = data["items"]
    os.makedirs(os.path.join(DOCS, "items"), exist_ok=True)
    os.makedirs(os.path.join(DOCS, "demos"), exist_ok=True)
    open(os.path.join(DOCS, ".nojekyll"), "w").close()

    # 首页：按发现日期分组，最近 6 天
    by_day = {}
    for it in items:
        by_day.setdefault(it["found"][:10], []).append(it)
    days = sorted(by_day, reverse=True)[:6]
    parts = ['<p style="margin:14px 0 0">'
             + pair("盯着：全双工语音、流式多模态模型、agent harness、座舱助手。"
                    "自动抓取 arXiv / GitHub / HuggingFace / HackerNews。",
                    "Watching: full-duplex speech, streaming multimodal models, "
                    "agent harnesses, cockpit assistants. Auto-curated from "
                    "arXiv / GitHub / HuggingFace / HackerNews.") + "</p>"]
    primer = os.path.join(DOCS, "demos", "full-duplex-primer.html")
    if os.path.exists(primer):
        parts.append('<p><a class="demo-link" href="' + BASE
                     + '/demos/full-duplex-primer.html">'
                     + pair("▶ 什么是全双工语音助手？（交互演示）",
                            "▶ What is a full-duplex voice assistant? (interactive)")
                     + "</a></p>")
    for d in days:
        rows = sorted(by_day[d], key=lambda x: -x["score"])
        parts.append(f'<h2 class="day">{d} · {len(rows)} '
                     + pair("条", "items") + "</h2>")
        parts += [card(it) for it in rows[:25]]
    open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8").write(
        shell("cockpit-agent-radar", "\n".join(parts)))

    # 子页
    for it in items:
        open(os.path.join(DOCS, "items", it["id"] + ".html"),
             "w", encoding="utf-8").write(item_page(it))

    # 存档：按月分组全量
    by_m = {}
    for it in items:
        by_m.setdefault(it["found"][:7], []).append(it)
    parts = []
    for m in sorted(by_m, reverse=True):
        parts.append(f'<h2 class="day">{m}</h2>')
        parts += [card(it) for it in sorted(by_m[m], key=lambda x: -x["score"])]
    open(os.path.join(DOCS, "archive.html"), "w", encoding="utf-8").write(
        shell("Archive · cockpit-agent-radar", "\n".join(parts)))

    open(os.path.join(DOCS, "feed.xml"), "w", encoding="utf-8").write(rss(items))
    print(f"site built: {len(items)} items, {len(days)} days on index")


if __name__ == "__main__":
    main()
