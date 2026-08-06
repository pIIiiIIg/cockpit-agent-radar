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
import re
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
.datebar { display:flex; gap:8px; align-items:center; margin:16px 0 2px; }
.datebar input[type=date] { background:var(--chip); color:var(--fg);
        border:1px solid var(--line); border-radius:6px; padding:3px 8px;
        font:inherit; font-size:13px; color-scheme:dark light; }
.datebar .btn.off { opacity:.35; pointer-events:none; }
h3.slot { font-size:13px; color:var(--dim); margin:16px 0 8px 8px; font-weight:600; }
.badge.new { background:#1f8f4d; color:#fff; font-weight:700; }
[data-lang="zh"] .l-en { display:none; } [data-lang="en"] .l-zh { display:none; }
.item-page .sum-block { background:var(--card); border:1px solid var(--line);
        border-radius:10px; padding:14px 16px; margin:14px 0; }
.deep-badge { color:#b98cff; font-weight:600; }
.explain { margin-top:22px; }
.explain h3 { font-size:15px; margin:22px 0 7px; padding-bottom:5px;
              border-bottom:1px solid var(--line); }
.explain p { margin:7px 0; }
.explain ul,.explain ol { margin:7px 0; padding-left:22px; }
.explain li { margin:5px 0; }
.explain .lead { border-left:3px solid var(--acc); padding:10px 14px;
                 background:var(--card); border-radius:0 8px 8px 0; }
.explain .editorial { border:1px solid var(--line); background:var(--chip);
                      border-radius:9px; padding:11px 14px; }
.explain .note { color:var(--dim); font-size:12.5px; margin-top:18px; }
.open-status { display:inline-block; border-radius:5px; padding:1px 7px;
               background:var(--chip); font-size:12px; font-weight:600; }
.open-status.open { color:#3fb46b; }
.open-status.partial { color:#e0a23f; }
.open-status.unavailable { color:#e06b6b; }
.pending-explain { color:var(--dim); border:1px dashed var(--line);
                   border-radius:9px; padding:12px 14px; margin-top:20px; }
.no-updates { background:var(--card); border:1px dashed var(--line);
              border-radius:10px; padding:16px; color:var(--dim); }
.reviews { border:1px solid var(--line); background:var(--card);
           border-radius:10px; padding:12px 14px; margin:14px 0 20px; }
.reviews h2 { font-size:15px; margin:0 0 8px; }
.review-row { padding:8px 0; border-top:1px solid var(--line); }
.review-row:first-of-type { border-top:0; }
.review-row .links { color:var(--dim); font-size:12.5px; margin-top:3px; }
.report-body { background:var(--card); border:1px solid var(--line);
               border-radius:10px; padding:18px 20px; margin-top:14px; }
.report-body h1,.report-body h2,.report-body h3 { line-height:1.35; }
.report-body h2 { margin-top:28px; border-bottom:1px solid var(--line); padding-bottom:5px; }
.report-body pre { overflow:auto; background:var(--bg); border:1px solid var(--line);
                   border-radius:7px; padding:11px; }
.report-body code { background:var(--chip); border-radius:4px; padding:1px 4px; }
.report-body pre code { background:none; padding:0; }
.report-body table { width:100%; border-collapse:collapse; margin:12px 0; font-size:13px; }
.report-body th,.report-body td { border:1px solid var(--line); padding:6px 8px; text-align:left; }
.report-body blockquote { margin:12px 0; padding:5px 14px; border-left:3px solid var(--acc);
                          color:var(--dim); }
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
  // 回看断点：比你上次打开首页时更新的条目标 NEW。
  // 基线只在首页翻新——翻旧日期页不会把"看到哪了"冲掉。
  document.addEventListener("DOMContentLoaded", function () {
    var seen = localStorage.getItem("radar-seen") || "";
    var maxF = seen;
    document.querySelectorAll(".card[data-found]").forEach(function (c) {
      var f = c.getAttribute("data-found");
      if (seen && f > seen) {
        var b = document.createElement("span");
        b.className = "badge new"; b.textContent = "NEW";
        var meta = c.querySelector(".meta");
        if (meta) meta.insertBefore(b, meta.firstChild);
      }
      if (f > maxF) maxF = f;
    });
    if (document.body.getAttribute("data-page") === "index" && maxF)
      localStorage.setItem("radar-seen", maxF);
  });
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
<body data-page="__PAGE__"><div class="wrap">
<header class="site">
  <h1><a href="__BASE__/" style="color:inherit">🚗 cockpit-agent-radar</a></h1>
  <span class="sub">__SUB__</span>
  <span class="toolbar">
    <button class="btn" onclick="toggleLang()">中 / EN</button>
    <a class="btn" href="__BASE__/feed.xml">RSS</a>
    <a class="btn" href="__BASE__/reviews.html">__REVIEWS_LABEL__</a>
    <a class="btn" href="__BASE__/reports/">__REPORTS_LABEL__</a>
    <a class="btn" href="__BASE__/archive.html">__ARCHIVE_LABEL__</a>
  </span>
</header>
__BODY__
<footer>__FOOTER__</footer>
</div></body></html>
"""


def shell(title, body, page=""):
    sub = pair("全双工 · 多模态 · 座舱语音 agent 技术雷达",
               "full-duplex · multimodal · cockpit voice-agent radar")
    foot = pair(
        "每天北京时间 9:00 / 14:00 / 19:00 自动更新 · 订阅 RSS 获取推送 · "
        '源码在 <a href="https://github.com/pIIiiIIg/cockpit-agent-radar">GitHub</a>',
        "Updates 9:00 / 14:00 / 19:00 (UTC+8) daily · subscribe via RSS · "
        '<a href="https://github.com/pIIiiIIg/cockpit-agent-radar">source</a>')
    return (SHELL.replace("__TITLE__", esc(title)).replace("__PAGE__", page)
            .replace("__BASE__", BASE)
            .replace("__STYLE__", STYLE).replace("__JS__", JS)
            .replace("__SUB__", sub).replace("__FOOTER__", foot)
            .replace("__REVIEWS_LABEL__", pair("精读记录", "Reviews"))
            .replace("__REPORTS_LABEL__", pair("日报", "Reports"))
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
    if it.get("explanation"):
        abstract_only = (it["explanation"].get("review_status")
                         == "abstract_backfill")
        meta.append(f'<span class="deep-badge">'
                    + (pair("◇ 摘要速读", "◇ abstract brief") if abstract_only
                       else pair("◆ 深度讲解", "◆ deep dive")) + "</span>")
    meta.append(f'<span title="进入雷达时刻">⏱ {esc(it["found"][11:16])}</span>')
    zh = it.get("summary_zh") or it.get("summary_en") or ""
    en = it.get("summary_en") or ""
    summ = (f'<div class="sum"><span class="l-zh">{esc(zh[:200])}</span>'
            f'<span class="l-en">{esc(en[:200])}</span></div>')
    return (f'<div class="card" data-found="{esc(it["found"])}">'
            f'<div class="t"><a href="{href}">{esc(it["title"])}'
            f'</a></div><div class="meta">{"".join(meta)}</div>{summ}</div>')


def slot_of(it):
    """found 时刻 → 班次标签。三班制：9 点班 / 14 点班 / 19 点班。"""
    h = int(it["found"][11:13])
    if h < 12:
        return "09:00"
    if h < 17:
        return "14:00"
    return "19:00"


def day_cards(rows):
    """一天内先按班次分组（晚班在前），班内按相关度排序。"""
    slots = {}
    for it in rows:
        slots.setdefault(slot_of(it), []).append(it)
    parts = []
    for s in sorted(slots, reverse=True):
        batch = sorted(slots[s], key=lambda x: -x["score"])
        parts.append(f'<h3 class="slot">⏰ {s} ' + pair("班", "run")
                     + f" · {len(batch)} " + pair("条", "items") + "</h3>")
        parts += [card(it) for it in batch]
    return parts


def no_updates():
    return ('<div class="no-updates">'
            + pair("本日扫描已完成，没有达到相关度门槛的新条目；持续跟踪项仍在更新。",
                   "Scan completed: no new items crossed the relevance threshold. "
                   "Existing watch items remain monitored.")
            + "</div>")


def load_review_history(valid_item_ids):
    path = os.path.join(ROOT, "data", "review_history.json")
    try:
        payload = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = []
    for raw in payload.get("entries", []):
        if (not isinstance(raw, dict) or raw.get("id") not in valid_item_ids
                or raw.get("review_status") != "editorial"
                or raw.get("source_depth") != "fulltext"):
            continue
        try:
            instant = datetime.fromisoformat(
                raw["reviewed_at"].replace("Z", "+00:00"))
            if instant.tzinfo is None:
                instant = instant.replace(tzinfo=CST)
            review_date = instant.astimezone(CST).date().isoformat()
        except (KeyError, AttributeError, TypeError, ValueError):
            continue
        if raw.get("review_date") != review_date:
            continue
        row = dict(raw)
        row["detail_url"] = f'{BASE}/items/{row["id"]}.html'
        paper_url = row.get("paper_url", "")
        row["paper_url"] = paper_url if re.match(r"^https?://", paper_url) else ""
        rows.append(row)
    return sorted(rows, key=lambda row: (row["reviewed_at"], row["id"]),
                  reverse=True)


def review_groups(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row.get("canonical_id") or row["id"], []).append(row)
    return list(groups.values())


def review_block(rows):
    """Stable per-day review section; mirror records share one visible row."""
    groups = review_groups(rows)
    parts = [
        '<section class="reviews"><h2>'
        + pair("今日完成精读", "Full-text reviews completed today")
        + f' · {len(groups)}</h2>'
    ]
    for group in groups:
        first = group[0]
        source_links = []
        detail_links = []
        for index, row in enumerate(group, 1):
            suffix = f" {index}" if len(group) > 1 else ""
            if row.get("paper_url"):
                source_links.append(
                    f'<a href="{esc(row["paper_url"])}" rel="noopener noreferrer">'
                    + pair("论文来源", "paper source") + suffix + "</a>")
            detail_links.append(
                f'<a href="{esc(row["detail_url"])}">'
                + pair("站内详情", "site detail") + suffix + "</a>")
        mirror = (" · " + pair(f"{len(group)} 个镜像已合并",
                                f"{len(group)} mirrors merged")
                  if len(group) > 1 else "")
        parts.append(
            f'<div class="review-row"><b>{esc(first.get("title"))}</b>{mirror}'
            f'<div class="links">{" · ".join(source_links + detail_links)}</div></div>')
    if not groups:
        parts.append('<div style="color:var(--dim)">'
                     + pair("0 篇；摘要速读不计入精读。",
                            "0 papers; abstract briefs are not counted.")
                     + "</div>")
    parts.append("</section>")
    return "".join(parts)


def build_reviews_page(by_review_day):
    parts = [
        f'<h2 class="day">{pair("精读历史", "Full-text review history")}</h2>',
        "<p>" + pair(
            "仅记录已升级为正文级人工复核的论文；摘要回填不计入。",
            "Only full-text editorial upgrades are listed; abstract backfills do not count."
        ) + "</p>",
    ]
    for day in sorted(by_review_day, reverse=True):
        rows = by_review_day[day]
        parts.append(
            f'<h2 class="day"><a href="{BASE}/days/{day}.html">{day}</a></h2>')
        parts.append(review_block(rows))
    if not by_review_day:
        parts.append(no_updates())
    with open(os.path.join(DOCS, "reviews.html"), "w",
              encoding="utf-8") as stream:
        stream.write(shell("Reviews · cockpit-agent-radar", "\n".join(parts)))


def _list_block(rows, ordered=False):
    rows = rows if isinstance(rows, list) else []
    clean = [row for row in rows if isinstance(row, str) and row.strip()]
    if not clean:
        return ""
    tag = "ol" if ordered else "ul"
    return f"<{tag}>" + "".join(f"<li>{esc(row)}</li>" for row in clean) + f"</{tag}>"


def _trusted_link(url, label):
    url = (url or "").strip()
    if not url.startswith("https://"):
        return ""
    return f'<a class="btn" href="{esc(url)}" rel="noopener noreferrer">{label}</a>'


def explanation_block(explanation):
    if not isinstance(explanation, dict) or not explanation.get("tl_dr"):
        return ('<div class="pending-explain">'
                + pair("深度讲解正在排队：自动增强通道会读取论文正文后补充。",
                       "Deep dive queued: the enhancement agent will read the paper and add it.")
                + "</div>")

    workflow = _list_block(explanation.get("workflow"), ordered=True)
    findings = _list_block(explanation.get("findings"))
    project_fit = _list_block(explanation.get("project_fit"))
    limitations = _list_block(explanation.get("limitations"))
    opened = explanation.get("open_source")
    opened = opened if isinstance(opened, dict) else {}
    status = opened.get("status", "unknown")
    status_labels = {
        "open": ("已开放", "Open"),
        "partial": ("部分开放", "Partial"),
        "unavailable": ("未开放", "Unavailable"),
        "unknown": ("未核验", "Unverified"),
    }
    zh_status, en_status = status_labels.get(status, status_labels["unknown"])
    links = " ".join(filter(None, [
        _trusted_link(opened.get("code_url"), pair("代码", "code")),
        _trusted_link(opened.get("model_url"), pair("模型", "model")),
    ]))

    source_depth = explanation.get("source_depth", "abstract")
    depth_label = pair("论文正文" if source_depth == "fulltext" else "摘要",
                       "full text" if source_depth == "fulltext" else "abstract")
    review = explanation.get("review_status", "auto")
    if review == "editorial":
        review_label = pair("人工复核", "editor-reviewed")
    elif review == "abstract_backfill":
        review_label = pair("摘要级自动整理，待正文升级",
                            "abstract backfill, awaiting full-text review")
    else:
        review_label = pair("自动生成", "auto-generated")
    section_title = (pair("摘要速读", "Abstract brief") if review == "abstract_backfill"
                     else pair("深度讲解", "Deep dive"))
    findings_section = (
        f'<h3>{pair("论文报告了什么", "Reported findings")}</h3>{findings}'
        if findings else "")
    workflow_section = (
        f'<h3>{pair("怎么工作", "How it works")}</h3>{workflow}'
        if workflow else "")
    limitations_section = (
        f'<h3>{pair("边界与局限", "Limits")}</h3>{limitations}'
        if limitations else "")

    return f"""
<section class="explain">
  <h2 style="margin:0 0 10px">{section_title}</h2>
  <p class="lead">{esc(explanation.get("tl_dr"))}</p>
  <h3>{pair("它解决什么问题", "Problem")}</h3>
  <p>{esc(explanation.get("problem"))}</p>
  <h3>{pair("核心方法", "Core method")}</h3>
  <p>{esc(explanation.get("method"))}</p>
{workflow_section}
{findings_section}
  <div class="editorial">
    <b>{pair("对 StreamingModelHarness 的帮助（编辑判断）",
             "Fit for StreamingModelHarness (editorial analysis)")}</b>
    {project_fit or '<p style="color:var(--dim)">—</p>'}
  </div>
{limitations_section}
  <h3>{pair("代码与模型开放情况", "Code and model availability")}</h3>
  <p><span class="open-status {esc(status)}">{pair(zh_status, en_status)}</span>
     &nbsp; {esc(opened.get("note"))}</p>
  <p>{links}</p>
  <p class="note">{pair("依据：", "Basis: ")}{depth_label} · {review_label}
     · {esc(explanation.get("generated_at", "")[:16].replace("T", " "))}</p>
</section>"""


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
    deep = explanation_block(it.get("explanation")) if it.get("kind") == "paper" else ""
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
{deep}
  <p><a class="btn" href="{esc(it["url"])}">{pair("→ 原文链接", "→ original link")}</a>
     &nbsp; <a class="btn" href="{BASE}/">{pair("← 返回列表", "← back")}</a></p>
  <div class="tags">{"".join(f'<span class="badge">{esc(t)}</span>' for t in it.get("tags", []))}</div>
</div>"""
    return shell(it["title"], body)


def datebar(cur, dates):
    """日期选择器 + 前后翻页。dates 为有内容的日期(降序)；选到没内容的日期给提示。"""
    i = dates.index(cur) if cur in dates else 0
    older = dates[i + 1] if i + 1 < len(dates) else None    # 更早的一天
    newer = dates[i - 1] if i > 0 else None                 # 更近的一天
    def nav(d, arrow, zh_t, en_t):
        if not d:
            return f'<span class="btn off">{arrow}</span>'
        return (f'<a class="btn" href="{BASE}/days/{d}.html" '
                f'title="{zh_t} {d}">{arrow}</a>')
    return f"""
<div class="datebar">
  {nav(older, "◀", "前一天", "prev")}
  <input type="date" id="dp" value="{cur}" min="{dates[-1]}" max="{dates[0]}">
  {nav(newer, "▶", "后一天", "next")}
  <span style="color:var(--dim);font-size:12.5px">{pair("选日期看当天内容", "pick a date")}</span>
</div>
<script>
var DATES = new Set({json.dumps(dates)});
document.getElementById("dp").onchange = function () {{
  if (DATES.has(this.value)) location.href = "{BASE}/days/" + this.value + ".html";
  else {{ this.style.borderColor = "#e0a23f";
         this.title = "该日期无内容 / no items on that day"; }}
}};
</script>"""


def md_inline(text):
    """Render a deliberately small, escaped Markdown inline subset."""
    value = esc(text)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" rel="noopener noreferrer">\1</a>',
        value)
    return value


def markdown_to_html(text):
    """Zero-dependency report renderer; raw HTML is always escaped."""
    lines = text.replace("\r\n", "\n").splitlines()
    out, paragraph, code = [], [], None
    list_kind = None

    def flush_paragraph():
        if paragraph:
            out.append("<p>" + " ".join(md_inline(x.strip()) for x in paragraph) + "</p>")
            paragraph.clear()

    def close_list():
        nonlocal list_kind
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None

    i = 0
    while i < len(lines):
        line = lines[i]
        if code is not None:
            if line.strip().startswith("```"):
                out.append("<pre><code>" + esc("\n".join(code)) + "</code></pre>")
                code = None
            else:
                code.append(line)
            i += 1
            continue
        if line.strip().startswith("```"):
            flush_paragraph(); close_list(); code = []
            i += 1; continue
        if not line.strip():
            flush_paragraph(); close_list(); i += 1; continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            flush_paragraph(); close_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{md_inline(heading.group(2))}</h{level}>")
            i += 1; continue

        # GitHub-style pipe tables.
        if (line.strip().startswith("|") and i + 1 < len(lines)
                and re.match(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$", lines[i + 1])):
            flush_paragraph(); close_list()
            headers = [cell.strip() for cell in line.strip().strip("|").split("|")]
            out.append("<table><thead><tr>" + "".join(
                f"<th>{md_inline(cell)}</th>" for cell in headers) + "</tr></thead><tbody>")
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [cell.strip() for cell in lines[i].strip().strip("|").split("|")]
                out.append("<tr>" + "".join(
                    f"<td>{md_inline(cell)}</td>" for cell in cells) + "</tr>")
                i += 1
            out.append("</tbody></table>")
            continue

        bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
        numbered = re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if bullet or numbered:
            flush_paragraph()
            wanted = "ul" if bullet else "ol"
            if list_kind != wanted:
                close_list(); out.append(f"<{wanted}>"); list_kind = wanted
            out.append("<li>" + md_inline((bullet or numbered).group(1)) + "</li>")
            i += 1; continue

        quote = re.match(r"^\s*>\s?(.*)$", line)
        if quote:
            flush_paragraph(); close_list()
            out.append("<blockquote>" + md_inline(quote.group(1)) + "</blockquote>")
            i += 1; continue

        paragraph.append(line)
        i += 1

    flush_paragraph(); close_list()
    if code is not None:
        out.append("<pre><code>" + esc("\n".join(code)) + "</code></pre>")
    return "\n".join(out)


def build_reports(by_review_day):
    source = os.path.join(ROOT, "reports")
    target = os.path.join(DOCS, "reports")
    os.makedirs(target, exist_ok=True)
    rows = []
    if os.path.isdir(source):
        for name in os.listdir(source):
            if not name.endswith(".md"):
                continue
            path = os.path.join(source, name)
            stem = name[:-3]
            match = re.search(r"(\d{4}-\d{2}-\d{2})$", stem)
            date = match.group(1) if match else ""
            kind = "daily" if stem.startswith("每日调研日报") else "detail"
            title = ("每日调研日报" if kind == "daily" else "全双工语音技术增量调研")
            text = open(path, encoding="utf-8").read()
            review_source = ""
            if by_review_day.get(date):
                review_source = (
                    f'<p><a class="btn" href="{BASE}/days/{date}.html">'
                    + pair("→ 当天精读来源", "→ full-text reviews for this day")
                    + "</a></p>")
            body = (f'<div class="item-page"><h2>{esc(title)} · {esc(date)}</h2>'
                    f'{review_source}'
                    f'<div class="report-body">{markdown_to_html(text)}</div>'
                    f'<p><a class="btn" href="{BASE}/reports/">'
                    + pair("← 返回日报", "← reports") + "</a></p></div>")
            output_name = stem + ".html"
            open(os.path.join(target, output_name), "w", encoding="utf-8").write(
                shell(f"{title} · {date}", body))
            rows.append({"date": date, "kind": kind, "title": title,
                         "href": f"{BASE}/reports/{output_name}"})
    rows.sort(key=lambda row: (row["date"], row["kind"]), reverse=True)
    valid_report_files = {
        row["href"].rsplit("/", 1)[-1] for row in rows} | {"index.html"}
    for name in os.listdir(target):
        if name.endswith(".html") and name not in valid_report_files:
            os.remove(os.path.join(target, name))
    cards = []
    for row in rows:
        label = pair("精简日报", "Daily brief") if row["kind"] == "daily" else pair(
            "详细调研", "Deep report")
        cards.append(
            f'<div class="card"><div class="t"><a href="{row["href"]}">'
            f'{esc(row["title"])} · {esc(row["date"])}</a></div>'
            f'<div class="meta"><span class="badge hi">{label}</span></div></div>')
    body = (f'<h2 class="day">{pair("每日调研", "Research reports")}</h2>'
            + ("".join(cards) if cards else no_updates()))
    open(os.path.join(target, "index.html"), "w", encoding="utf-8").write(
        shell("Reports · cockpit-agent-radar", body))
    return rows


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
    try:
        explanations = json.load(open(
            os.path.join(ROOT, "data", "explanations.json"), encoding="utf-8"))
        explanations = explanations if isinstance(explanations, dict) else {}
    except Exception:
        explanations = {}
    for item in items:
        item["explanation"] = explanations.get(item["id"], {})
    history = load_review_history({item["id"] for item in items})
    by_review_day = {}
    for row in history:
        by_review_day.setdefault(row["review_date"], []).append(row)
    items_dir = os.path.join(DOCS, "items")
    os.makedirs(items_dir, exist_ok=True)
    valid_item_files = {item["id"] + ".html" for item in items}
    for name in os.listdir(items_dir):
        if name.endswith(".html") and name not in valid_item_files:
            os.remove(os.path.join(items_dir, name))
    os.makedirs(os.path.join(DOCS, "demos"), exist_ok=True)
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    reports = build_reports(by_review_day)
    build_reviews_page(by_review_day)

    # 按发现日期分组；首页放最近 6 天，每天另出独立子页 days/<date>.html
    by_day = {}
    for it in items:
        by_day.setdefault(it["found"][:10], []).append(it)
    scan_day = (data.get("generated") or "")[:10]
    all_days = sorted(set(by_day) | set(by_review_day)
                      | ({scan_day} if scan_day else set()),
                      reverse=True)
    days = all_days[:6]
    os.makedirs(os.path.join(DOCS, "days"), exist_ok=True)
    days_dir = os.path.join(DOCS, "days")
    for name in os.listdir(days_dir):
        if name.endswith(".html") and name[:-5] not in all_days:
            os.remove(os.path.join(days_dir, name))
    for d in all_days:
        rows = by_day.get(d, [])
        body = (datebar(d, all_days)
                + review_block(by_review_day.get(d, []))
                + f'<h2 class="day">{d} · {len(rows)} ' + pair("条", "items") + "</h2>"
                + ("\n".join(day_cards(rows)) if rows else no_updates())
                + f'<p style="margin-top:18px"><a class="btn" href="{BASE}/">'
                + pair("← 最新", "← latest") + "</a></p>")
        open(os.path.join(DOCS, "days", d + ".html"), "w", encoding="utf-8").write(
            shell(f"{d} · cockpit-agent-radar", body))
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
    if reports:
        latest_date = reports[0]["date"]
        parts.append('<p><a class="demo-link" href="' + BASE + '/reports/">'
                     + pair(f"◆ 最新每日调研：{latest_date}",
                            f"◆ Latest research report: {latest_date}")
                     + "</a></p>")
    parts.append(datebar(all_days[0], all_days))
    for d in days:
        rows = by_day.get(d, [])
        parts.append(f'<h2 class="day"><a href="{BASE}/days/{d}.html" '
                     f'style="color:inherit">{d}</a> · {len(rows)} '
                     + pair("条", "items") + "</h2>")
        if rows:
            parts += day_cards(rows)
        else:
            parts.append(no_updates())
    open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8").write(
        shell("cockpit-agent-radar", "\n".join(parts), page="index"))

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
    explained = sum(bool(item.get("explanation")) for item in items
                    if item.get("kind") == "paper")
    papers = sum(item.get("kind") == "paper" for item in items)
    print(f"site built: {len(items)} items, {len(days)} days on index, "
          f"paper deep dives {explained}/{papers}, reports {len(reports)}")


if __name__ == "__main__":
    main()
