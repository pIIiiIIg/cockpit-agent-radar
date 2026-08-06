#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the public, bilingual automation-system guide.

The facts and page structure live here; docs/automation is generated output.
The renderer deliberately has no template/runtime dependency.
"""
import html
import json
import os
import re
from datetime import datetime


BASE = "https://piiiiiig.github.io/cockpit-agent-radar"

STAGES = [
    ("research", "论文调研", "Research", "抓取、去重、摘要与全文精读",
     "Fetch, deduplicate, brief, and review full text", "mixed"),
    ("reports", "问题驱动日报", "Reports", "把论文证据映射到项目问题和实验",
     "Map evidence to project problems and experiments", "cursor"),
    ("candidates", "实验候选", "Candidates", "拆成单变量候选并隔离实现",
     "Turn advice into isolated, single-variable changes", "cursor"),
    ("h20", "H20 隔离评测", "H20 evaluation", "双 worker、真实音频、分层测试",
     "Two workers, real audio, staged evaluation", "script"),
    ("selection", "选择与留存", "Selection", "硬门、Pareto、partial 与负结果",
     "Hard gates, Pareto, partial retention, negative results", "script"),
    ("publishing", "发布与反馈", "Publishing", "实验分支、registry、Pages 与下一日报",
     "Experiment branches, registry, Pages, and feedback", "script"),
    ("limitations", "局限与证据审计", "Limitations & audit",
     "基线、证据缺口、指标边界与 99% 声明门槛",
     "Baselines, evidence gaps, metric boundaries, and the 99% claim gate",
     "mixed"),
]


def esc(value):
    return html.escape(str(value or ""), quote=True)


def pair(zh, en, tag="span"):
    return (f'<{tag} class="l-zh">{esc(zh)}</{tag}>'
            f'<{tag} class="l-en">{esc(en)}</{tag}>')


def safe_json(path, fallback):
    """Load JSON without letting missing or malformed data break the guide."""
    try:
        with open(path, encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError, TypeError):
        return fallback


def safe_http_url(value):
    value = value if isinstance(value, str) else ""
    return value if re.match(r"^https?://", value) else ""


def load_snapshot(root):
    """Derive all automation-page facts from the publishable source data."""
    data_dir = os.path.join(root, "data")
    item_payload = safe_json(os.path.join(data_dir, "items.json"), {})
    has_items = (isinstance(item_payload, dict)
                 and isinstance(item_payload.get("items"), list))
    raw_items = item_payload["items"] if has_items else []
    items = [row for row in raw_items if isinstance(row, dict)]
    item_by_id = {
        row["id"]: row for row in items
        if isinstance(row.get("id"), str) and re.match(r"^[A-Za-z0-9_-]+$", row["id"])
    }
    papers = [row for row in item_by_id.values() if row.get("kind") == "paper"]
    paper_ids = {row["id"] for row in papers}

    raw_explanations = safe_json(
        os.path.join(data_dir, "explanations.json"), {})
    explanations = raw_explanations if isinstance(raw_explanations, dict) else {}
    fulltext_ids = {
        iid for iid, row in explanations.items()
        if iid in paper_ids and isinstance(row, dict)
        and row.get("review_status") == "editorial"
        and row.get("source_depth") == "fulltext"
    }
    abstract_ids = {
        iid for iid, row in explanations.items()
        if iid in paper_ids and isinstance(row, dict)
        and row.get("review_status") == "abstract_backfill"
    }

    history_payload = safe_json(
        os.path.join(data_dir, "review_history.json"), {})
    raw_history = (history_payload.get("entries", [])
                   if isinstance(history_payload, dict) else [])
    history = []
    for row in raw_history:
        if (not isinstance(row, dict) or row.get("id") not in paper_ids
                or row.get("review_status") != "editorial"
                or row.get("source_depth") != "fulltext"
                or not re.match(r"^\d{4}-\d{2}-\d{2}$",
                                str(row.get("review_date", "")))):
            continue
        history.append(row)
    latest_review_date = max(
        (row["review_date"] for row in history), default="")
    latest_rows = [
        row for row in history if row["review_date"] == latest_review_date]
    latest_rows.sort(
        key=lambda row: (str(row.get("reviewed_at", "")), row["id"]),
        reverse=True)
    latest_papers = []
    seen_canonical = set()
    for row in latest_rows:
        canonical = row.get("canonical_id") or row.get("mirror_of") or row["id"]
        if canonical in seen_canonical:
            continue
        seen_canonical.add(canonical)
        item = item_by_id[row["id"]]
        paper_url = safe_http_url(row.get("paper_url") or item.get("url"))
        latest_papers.append({
            "id": row["id"],
            "title": row.get("title") or item.get("title") or row["id"],
            "paper_url": paper_url,
        })

    report_rows = []
    report_dir = os.path.join(root, "reports")
    try:
        report_names = os.listdir(report_dir)
    except OSError:
        report_names = []
    pattern = re.compile(
        r"^(每日调研日报|全双工语音技术增量调研)-(\d{4}-\d{2}-\d{2})\.md$")
    for name in report_names:
        match = pattern.match(name)
        if not match:
            continue
        kind = "daily" if match.group(1) == "每日调研日报" else "detail"
        report_rows.append({
            "kind": kind,
            "date": match.group(2),
            "title": match.group(1),
            "href": f"{BASE}/reports/{name[:-3]}.html",
        })
    report_rows.sort(key=lambda row: (row["date"], row["kind"]), reverse=True)
    latest_reports = {}
    for row in report_rows:
        latest_reports.setdefault(row["kind"], row)

    found_days = {
        str(row.get("found", ""))[:10] for row in items
        if re.match(r"^\d{4}-\d{2}-\d{2}", str(row.get("found", "")))
    }
    scan_day = str(item_payload.get("generated", ""))[:10]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", scan_day):
        found_days.add(scan_day)
    all_days = found_days | {row["review_date"] for row in history}
    latest_day = max(all_days, default="")
    build_time = datetime.now().astimezone()
    return {
        "available": has_items,
        "total_items": len(items),
        "paper_count": len(papers),
        "fulltext_count": len(fulltext_ids),
        "abstract_count": len(abstract_ids),
        "history_count": len(history),
        "latest_review_date": latest_review_date,
        "latest_review_count": len(latest_rows),
        "latest_papers": latest_papers,
        "latest_day": latest_day,
        "latest_reports": latest_reports,
        "report_days": len({row["date"] for row in report_rows}),
        "report_count": len(report_rows),
        "build_date": build_time.date().isoformat(),
        "build_time": build_time.isoformat(timespec="minutes"),
    }


def empty_snapshot():
    return load_snapshot(os.path.join(os.path.dirname(__file__), "__missing__"))


STYLE = r"""
:root{--bg:#0e1116;--card:#161b23;--fg:#dbe2ea;--dim:#8b96a5;--acc:#4da3ff;
--ok:#3fb46b;--warn:#e0a23f;--bad:#e06b6b;--violet:#b98cff;--line:#29313d;
--chip:#1d2733} @media(prefers-color-scheme:light){:root{--bg:#f7f8fa;--card:#fff;
--fg:#1c2430;--dim:#5d6b7c;--acc:#0d6ecc;--ok:#1f8f4d;--warn:#a66d0b;
--bad:#b34242;--violet:#7542b5;--line:#dce2ea;--chip:#eef2f7}}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);
color:var(--fg);font:15px/1.7 system-ui,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
a{color:var(--acc);text-decoration:none}a:hover{text-decoration:underline}
a:focus-visible,button:focus-visible{outline:3px solid var(--acc);outline-offset:3px}
.wrap{max-width:1040px;margin:auto;padding:18px 18px 64px}.site{display:flex;gap:12px;
align-items:center;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:13px}
.brand{font-size:19px;font-weight:700;color:var(--fg)}.sub{font-size:12px;color:var(--dim)}
.toolbar{margin-left:auto;display:flex;gap:7px;flex-wrap:wrap}.btn{display:inline-flex;align-items:center;
gap:5px;background:var(--chip);color:var(--fg);border:1px solid var(--line);border-radius:7px;
padding:5px 10px;font:inherit;font-size:12.5px;cursor:pointer}.btn:hover{border-color:var(--acc);
text-decoration:none}.hero{padding:28px 0 12px}.hero h1{font-size:clamp(25px,4vw,40px);
line-height:1.2;margin:0 0 12px}.hero p{max-width:820px;color:var(--dim);font-size:16px}
.legend,.controls{display:flex;gap:9px;flex-wrap:wrap;align-items:center;margin:15px 0}
.badge{display:inline-block;border:1px solid var(--line);background:var(--chip);border-radius:999px;
padding:2px 8px;font-size:12px}.cursor{color:var(--violet)}.script{color:var(--acc)}
.mixed{color:var(--warn);border-color:var(--warn)}
.verified{color:var(--ok)}.pending{color:var(--warn)}.fact{color:var(--ok)}
.flow{display:grid;grid-template-columns:repeat(7,1fr);gap:18px;margin:24px 0 34px;
padding:8px 0;position:relative}.flow:before{content:"";position:absolute;left:6%;right:6%;top:53px;
height:2px;background:var(--line)}.flow-node{position:relative;z-index:1;background:var(--card);
border:1px solid var(--line);border-radius:12px;padding:14px 12px;min-height:150px;color:var(--fg);
transition:.2s transform,.2s border-color,.2s box-shadow}.flow-node:hover,.flow-node.active{
border-color:var(--acc);box-shadow:0 0 0 3px color-mix(in srgb,var(--acc) 18%,transparent);
transform:translateY(-3px);text-decoration:none}.flow-node .num{display:grid;place-items:center;width:28px;
height:28px;border-radius:50%;background:var(--acc);color:white;font-weight:700;margin-bottom:10px}
.flow-node h2{font-size:15px;margin:0 0 6px}.flow-node p{font-size:12.5px;color:var(--dim);margin:0}
.flow-node.pulse:after{content:"";position:absolute;inset:-4px;border:2px solid var(--acc);
border-radius:15px;animation:pulse 1.2s ease-out}.section{margin:28px 0}.section h2{font-size:21px;
border-left:3px solid var(--acc);padding-left:10px}.grid{display:grid;
grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}.card{background:var(--card);
border:1px solid var(--line);border-radius:11px;padding:15px}.card h3{font-size:15px;margin:0 0 7px}
.card p,.card li{font-size:13.5px}.card p{color:var(--dim)}.card ul,.card ol{padding-left:20px}
.callout{border-left:3px solid var(--warn);background:var(--card);padding:12px 15px;
border-radius:0 9px 9px 0}.callout.ok{border-color:var(--ok)}.callout.bad{border-color:var(--bad)}
.steps{counter-reset:step}.step{position:relative;margin:0 0 12px 38px;padding:13px 15px;
background:var(--card);border:1px solid var(--line);border-radius:10px}.step:before{counter-increment:step;
content:counter(step);position:absolute;left:-39px;top:12px;width:28px;height:28px;display:grid;
place-items:center;border-radius:50%;background:var(--acc);color:white;font-weight:700}
.step h3{margin:0 0 4px;font-size:15px}.step p{margin:4px 0;color:var(--dim)}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:10px}
.metric{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.metric b{display:block;font-size:24px;color:var(--acc)}.metric small{color:var(--dim)}
.artifacts{display:grid;gap:10px}.artifact{border-bottom:1px solid var(--line);padding:0 0 10px}
.artifact:last-child{border-bottom:0;padding-bottom:0}.artifact p{margin:3px 0}
.funnel{display:grid;gap:8px}.funnel-row{display:grid;grid-template-columns:minmax(145px,1fr) 3fr 55px;
gap:10px;align-items:center;font-size:13px}.funnel-track{height:12px;background:var(--chip);
border-radius:999px;overflow:hidden}.funnel-fill{height:100%;min-width:3px;background:var(--acc);
border-radius:999px;transition:width .45s ease}.funnel-row:nth-child(3) .funnel-fill{background:var(--violet)}
.funnel-row:nth-child(4) .funnel-fill{background:var(--ok)}
.audit-banner{border:1px solid var(--warn);background:color-mix(in srgb,var(--warn) 9%,var(--card));
border-radius:11px;padding:14px 16px}.compare{display:grid;grid-template-columns:repeat(3,1fr);
gap:12px}.compare .card{position:relative}.compare .card:after{content:"→";position:absolute;
right:-18px;top:44%;color:var(--dim);font-size:20px}.compare .card:last-child:after{display:none}
.evidence-table{width:100%;border-collapse:collapse;font-size:13px}.evidence-table th,
.evidence-table td{border:1px solid var(--line);padding:8px;vertical-align:top;text-align:left}
.evidence-table th{background:var(--chip)}.risk-grid{display:grid;
grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}.risk{border-left:4px solid var(--warn)}
.risk.high{border-left-color:var(--bad)}.risk.medium{border-left-color:var(--warn)}
.maturity{display:grid;gap:9px}.maturity-row{display:grid;grid-template-columns:minmax(150px,1fr) 2fr;
gap:10px;align-items:center}.maturity-track{height:12px;background:var(--chip);border-radius:999px;
overflow:hidden}.maturity-fill{height:100%;background:var(--warn);border-radius:999px}
.maturity-fill.low{width:22%}.maturity-fill.partial{width:52%}.maturity-fill.strong{width:82%;
background:var(--ok)}details{background:var(--card);border:1px solid var(--line);border-radius:9px;
padding:10px 13px;margin:8px 0}summary{cursor:pointer;font-weight:650}
.decision-tree{display:grid;gap:9px;counter-reset:gate}.decision-tree details{margin:0 0 0 28px;
position:relative}.decision-tree details:before{counter-increment:gate;content:counter(gate);
position:absolute;left:-32px;top:9px;width:23px;height:23px;display:grid;place-items:center;
border-radius:50%;background:var(--acc);color:#fff;font-weight:700;font-size:12px}
.tree-outcomes{display:flex;gap:7px;flex-wrap:wrap;margin:10px 0 0 28px}.tree-outcomes .badge{
font-size:13px;padding:5px 10px}.verdict{border-top:3px solid var(--line)}
.verdict.good{border-color:var(--ok)}.verdict.warn{border-color:var(--warn)}
.verdict.bad{border-color:var(--bad)}.plain-analogy{font-size:16px}
.timeline{border-left:2px solid var(--line);margin-left:11px}.event{position:relative;margin:0 0 14px 25px;
padding:11px 14px;background:var(--card);border:1px solid var(--line);border-radius:9px}
.event:before{content:"";position:absolute;left:-32px;top:17px;width:12px;height:12px;
border-radius:50%;background:var(--acc);box-shadow:0 0 0 4px var(--bg)}
.decision{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.decision .card{text-align:center}
.arrow{color:var(--dim);font-size:22px;text-align:center}.term{border-bottom:1px dotted var(--dim);
cursor:help}.navline{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;margin-top:38px;
padding-top:16px;border-top:1px solid var(--line)}.navline a:last-child{text-align:right}
footer{color:var(--dim);font-size:12px;margin-top:35px}.l-en{display:none}
[data-lang=en] .l-en{display:revert}[data-lang=en] .l-zh{display:none}
@keyframes pulse{from{opacity:1;transform:scale(1)}to{opacity:0;transform:scale(1.07)}}
@media(max-width:820px){.flow{grid-template-columns:repeat(2,1fr)}.flow:before{display:none}
.decision,.compare{grid-template-columns:1fr}.compare .card:after{display:none}.site .sub{display:none}
.evidence-table{display:block;overflow-x:auto}}@media(max-width:480px){
.wrap{padding:12px 12px 48px}.flow{grid-template-columns:1fr}.toolbar{margin-left:0;width:100%}
.hero{padding-top:20px}.navline{grid-template-columns:1fr}.navline a:last-child{text-align:left}
.funnel-row{grid-template-columns:1fr 2fr 42px}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;
transition:none!important;scroll-behavior:auto!important}.flow-node.pulse:after{display:none}}
"""

JS = r"""
(function(){
 var root=document.documentElement, reduced=matchMedia("(prefers-reduced-motion: reduce)").matches;
 root.dataset.lang=localStorage.getItem("radar-lang")||
   (navigator.language&&navigator.language.indexOf("zh")===0?"zh":"en");
 window.toggleLang=function(){root.dataset.lang=root.dataset.lang==="zh"?"en":"zh";
   localStorage.setItem("radar-lang",root.dataset.lang)};
 var nodes=[].slice.call(document.querySelectorAll(".flow-node")),timer=null,index=-1;
 function show(i){nodes.forEach(function(n){n.classList.remove("active","pulse")});
   if(nodes[i]){nodes[i].classList.add("active");if(!reduced)nodes[i].classList.add("pulse")}}
 function step(){if(!nodes.length)return;index=(index+1)%nodes.length;show(index)}
 window.playFlow=function(){if(reduced){step();return}clearInterval(timer);step();timer=setInterval(step,1500)}
 window.pauseFlow=function(){clearInterval(timer);timer=null}
 window.resetFlow=function(){clearInterval(timer);timer=null;index=-1;show(-1)}
 document.addEventListener("keydown",function(e){if(e.key==="Escape")window.resetFlow()});
})();
"""


def header():
    return f"""<header class="site">
<a class="brand" href="{BASE}/">🚗 cockpit-agent-radar</a>
<span class="sub">{pair("自动化系统讲解","automation system guide")}</span>
<nav class="toolbar" aria-label="Site">
<a class="btn" href="{BASE}/automation/">{pair("自动化","Automation")}</a>
<a class="btn" href="{BASE}/reviews.html">{pair("精读","Reviews")}</a>
<a class="btn" href="{BASE}/reports/">{pair("日报","Reports")}</a>
<button class="btn" type="button" onclick="toggleLang()" aria-label="Switch language">中 / EN</button>
</nav></header>"""


def navline(slug):
    slugs = [row[0] for row in STAGES]
    if slug == "case-hybrid-c":
        prev_slug, next_slug = "limitations", None
    else:
        index = slugs.index(slug)
        prev_slug = slugs[index - 1] if index else None
        next_slug = slugs[index + 1] if index + 1 < len(slugs) else "case-hybrid-c"
    def link(target, zh, en):
        if not target:
            return "<span></span>"
        return f'<a class="btn" href="{BASE}/automation/{target}/">{pair(zh,en)}</a>'
    return ('<nav class="navline" aria-label="Guide sequence">'
            + link(prev_slug, "← 上一环节", "← Previous")
            + f'<a class="btn" href="{BASE}/automation/">{pair("返回总览","Overview")}</a>'
            + link(next_slug, "下一环节 →", "Next →") + "</nav>")


def shell(title_zh, title_en, slug, body, snapshot=None):
    snapshot = snapshot or empty_snapshot()
    return f"""<!doctype html><html lang="zh" data-lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title_zh)} · cockpit-agent-radar</title><style>{STYLE}</style></head>
<body><div class="wrap">{header()}<main id="main">{body}</main>{navline(slug)}
<footer>{pair(f"事实状态构建于 {snapshot['build_date']}；实测与待验证严格分开。",f"Evidence status built on {snapshot['build_date']}; measured and pending claims are separated.")}</footer>
</div><script>{JS}</script></body></html>"""


def hero(zh, en, intro_zh, intro_en, badges=""):
    return (f'<section class="hero"><h1>{pair(zh,en)}</h1><p>{pair(intro_zh,intro_en)}</p>'
            f'<div class="legend">{badges}</div></section>')


def stage_links():
    labels = {
        "cursor": ("Cursor 参与", "Cursor-assisted"),
        "script": ("确定性脚本", "Deterministic scripts"),
        "mixed": ("混合：脚本 + Cursor", "Mixed: scripts + Cursor"),
    }
    rows = []
    for i, (slug, zh, en, dzh, den, owner) in enumerate(STAGES, 1):
        owner_zh, owner_en = labels[owner]
        rows.append(f"""<a class="flow-node" href="{BASE}/automation/{slug}/">
<span class="num">{i}</span><h2>{pair(zh,en)}</h2><p>{pair(dzh,den)}</p>
<span class="badge {owner}">{pair(owner_zh,owner_en)}</span></a>""")
    return "".join(rows)


def overview(snapshot=None):
    snapshot = snapshot or empty_snapshot()
    badges = (f'<span class="badge cursor">{pair("紫：Cursor 模型参与","Violet: Cursor-assisted")}</span>'
              f'<span class="badge script">{pair("蓝：确定性脚本","Blue: deterministic scripts")}</span>'
              f'<span class="badge mixed">{pair("金：脚本抓取/评分 + Cursor 全文精读","Gold: scripted fetch/score + Cursor full-text review")}</span>'
              f'<span class="badge verified">{pair("网站自动化：已实测","Site automation: verified")}</span>'
              f'<span class="badge pending">{pair("Harness 00:30 首跑：待验证","Harness first 00:30 run: pending")}</span>')
    body = hero("从技术雷达到可验证改进", "From radar to verified improvements",
        "这不是“让模型自动改代码”一个动作，而是一条有证据、有隔离、有硬门、可回滚的闭环。点击节点看输入、输出、失败边界与责任归属。",
        "This is not one “let a model edit code” action. It is an evidence-backed, isolated, gated, reversible loop. Open any node for inputs, outputs, and failure boundaries.", badges)
    body += f"""<div class="controls" aria-label="Flow animation">
<button class="btn" onclick="playFlow()">▶ {pair("逐步播放","Play")}</button>
<button class="btn" onclick="pauseFlow()">Ⅱ {pair("暂停","Pause")}</button>
<button class="btn" onclick="resetFlow()">↺ {pair("重置","Reset")}</button>
<span class="sub">{pair("Esc 也可重置；减少动态效果时仅单步高亮。","Esc resets; reduced-motion mode only steps.")}</span></div>
<div class="flow" aria-label="Automation flow">{stage_links()}</div>
<section class="section"><h2>{pair("一圈如何闭合","How the loop closes")}</h2><div class="steps">
<article class="step"><h3>{pair("发现证据","Discover evidence")}</h3><p>{pair("脚本抓取 arXiv、GitHub、Hugging Face 与 Hacker News；摘要回填保障没有 Cursor 时网站也能更新。","Scripts scan arXiv, GitHub, Hugging Face, and Hacker News. Abstract backfill keeps the site useful without Cursor.")}</p></article>
<article class="step"><h3>{pair("把证据变成问题","Turn evidence into questions")}</h3><p>{pair("Cursor 读取全文和 StreamingModelHarness 快照，写出“项目问题→证据→实验→成功门槛”，不是资讯摘要列表。","Cursor reads full text and the project snapshot, producing problem→evidence→experiment→success gate, not a news list.")}</p></article>
<article class="step"><h3>{pair("隔离实现与评测","Implement and evaluate in isolation")}</h3><p>{pair("候选在独立 worktree 实现，GPU4/5 与 GPU6/7 两个 worker 分开跑 smoke、452 组合和 122 复杂意图。","Candidates are implemented in worktrees and evaluated on separate GPU4/5 and GPU6/7 workers: smoke, 452 combinations, then 122 complex intents.")}</p></article>
<article class="step"><h3>{pair("只让证据进入主线","Only evidence advances")}</h3><p>{pair("99% 准确率和 1.6s P95 是硬门；失败方案也登记。可解释、可组合的局部收益进入 retained components，反馈下一日报。","99% accuracy and 1.6s P95 are hard gates. Failures are recorded; composable partial gains enter retained components and inform the next report.")}</p></article>
</div></section>
<section class="section"><h2>{pair("当前证据状态","Current evidence status")}</h2><div class="grid">
<article class="card"><h3 class="verified">{pair("已实测：Radar 网站自动化","Verified: Radar site automation")}</h3><p>{pair("三班抓取、摘要回填、测试、建站、推送、Pages smoke；本地日报/精读发布使用互斥锁、重试和完成哨兵。","Scheduled fetch, backfill, tests, build, push, and Pages smoke; local publishers use a mutex, retry, and completion sentinel.")}</p></article>
<article class="card"><h3 class="pending">{pair("待验证：Harness 首次 00:30 定时实跑","Pending: first Harness 00:30 scheduled run")}</h3><p>{pair("设计、脚本与资源隔离可说明，但首次无人值守定时结果尚未发生，不能写成“已稳定运行”。","The design, scripts, and resource isolation can be documented, but the first unattended scheduled result has not happened and is not claimed as stable.")}</p></article>
</div></section>
<p class="callout ok"><b>{pair("完整案例：","Full case:")}</b> <a href="{BASE}/automation/case-hybrid-c/">{pair("Hybrid C 为什么在 452 全量前只能局部留存 →","Why Hybrid C remains scoped before a full 452-case run →")}</a></p>"""
    return shell("自动化系统总览", "Automation overview", "research", body, snapshot).replace(
        navline("research"), "")


def metric_value(snapshot, key):
    return str(snapshot[key]) if snapshot.get("available") else "—"


def artifact_links(snapshot):
    parts = [
        f'<div class="artifact"><p><a href="{BASE}/reviews.html">'
        + pair("精读历史", "Full-text review history") + "</a></p></div>"
    ]
    if snapshot.get("latest_day"):
        day = esc(snapshot["latest_day"])
        parts.append(
            f'<div class="artifact"><p><a href="{BASE}/days/{day}.html">'
            + pair(f"最新 day 页 · {day}", f"Latest day page · {day}")
            + "</a></p></div>")
    papers = snapshot.get("latest_papers", [])[:5]
    if papers:
        rows = []
        for paper in papers:
            detail = f"{BASE}/items/{esc(paper['id'])}.html"
            source = (
                f' · <a href="{esc(paper["paper_url"])}" '
                'rel="noopener noreferrer">'
                + pair("原论文", "Original paper") + "</a>"
                if paper.get("paper_url") else "")
            rows.append(
                f'<li><a href="{detail}">{esc(paper["title"])}</a>{source}</li>')
        parts.append(
            '<div class="artifact"><p><b>'
            + pair("最新精读论文（镜像已合并）",
                   "Latest full-text reviews (mirrors merged)")
            + "</b></p><ul>" + "".join(rows) + "</ul></div>")
    report_labels = {
        "detail": ("最新详细增量调研", "Latest detailed incremental research"),
        "daily": ("最新每日调研日报", "Latest daily research brief"),
    }
    for kind in ("detail", "daily"):
        report = snapshot.get("latest_reports", {}).get(kind)
        if report:
            zh, en = report_labels[kind]
            parts.append(
                f'<div class="artifact"><p><a href="{esc(report["href"])}">'
                + pair(f"{zh} · {report['date']}", f"{en} · {report['date']}")
                + "</a></p></div>")
    parts.append(
        f'<div class="artifact"><p><a href="{BASE}/reports/">'
        + pair("全部报告索引", "All reports index") + "</a></p></div>")
    return "".join(parts)


def funnel(snapshot):
    total = snapshot.get("total_items", 0) if snapshot.get("available") else 0
    rows = [
        ("总收录", "Collected", snapshot.get("total_items", 0)),
        ("有效论文", "Papers", snapshot.get("paper_count", 0)),
        ("摘要速读 / 正文精读", "Abstract / full text",
         snapshot.get("abstract_count", 0) + snapshot.get("fulltext_count", 0)),
        ("报告覆盖天数", "Report days", snapshot.get("report_days", 0)),
    ]
    rendered = []
    for zh, en, value in rows:
        width = min(100, max(0, round(value * 100 / max(total, 1))))
        display = str(value) if snapshot.get("available") else "—"
        rendered.append(
            f'<div class="funnel-row"><span>{pair(zh,en)}</span>'
            f'<span class="funnel-track"><span class="funnel-fill" '
            f'style="display:block;width:{width}%"></span></span>'
            f'<b>{display}</b></div>')
    return "".join(rendered)


def research(snapshot=None):
    snapshot = snapshot or empty_snapshot()
    body = hero("论文调研", "Research",
        "调研层先用确定性脚本扩大召回，再让 Cursor 只处理值得全文精读的证据；“摘要速读”和“正文精读”在页面上明确分级。",
        "Deterministic scripts maximize recall; Cursor spends time only on evidence worth full-text review. Abstract briefs and full-text reviews remain visibly distinct.",
        '<span class="badge mixed">Mixed ownership</span><span class="badge script">Fetch/score: scripts</span><span class="badge cursor">Full text: Cursor</span><span class="badge verified">3 runs/day verified</span>')
    body += f"""<section class="section"><h2>{pair("当前真实数据","Current live data")}</h2>
<div class="metrics">
<div class="metric"><b>{metric_value(snapshot, "total_items")}</b><small>{pair("总收录条目","collected items")}</small></div>
<div class="metric"><b>{metric_value(snapshot, "paper_count")}</b><small>{pair("有效论文数","valid papers")}</small></div>
<div class="metric"><b>{metric_value(snapshot, "fulltext_count")}</b><small>{pair("editorial + fulltext 精读","editorial + fulltext reviews")}</small></div>
<div class="metric"><b>{metric_value(snapshot, "abstract_count")}</b><small>abstract_backfill</small></div>
<div class="metric"><b>{metric_value(snapshot, "history_count")}</b><small>{pair("review history 有效记录","valid review-history records")}</small></div>
<div class="metric"><b>{esc(snapshot.get("latest_review_date") or "—")} · {snapshot.get("latest_review_count", 0) if snapshot.get("latest_review_date") else "—"}</b><small>{pair("最新精读日期 · 当天数量","latest review date · count")}</small></div>
</div>
<p class="sub">{pair(
    "定义：收录仅计 items.json 的对象；有效论文为其中 kind=paper 且 ID 可发布的条目；正文精读来自 explanations.json 的 editorial+fulltext；摘要速读仅计 abstract_backfill；历史记录还须关联有效论文且状态、深度和日期合法。镜像只在链接列表合并，不篡改原始记录计数。构建时间：",
    "Definitions: collected counts object rows in items.json; valid papers have kind=paper and a publishable ID; full-text reviews are editorial+fulltext in explanations.json; abstract briefs count only abstract_backfill; history records must also reference a valid paper with valid status, depth, and date. Mirrors are merged only in the link list, without altering source-record counts. Built:")} {esc(snapshot["build_time"])}</p>
</section>
<section class="section"><h2>{pair("动态调研漏斗","Live research funnel")}</h2><div class="card funnel">{funnel(snapshot)}</div></section>
<section class="section"><h2>{pair("查看真实产物","Open real artifacts")}</h2><div class="card artifacts">{artifact_links(snapshot)}</div></section>
<section class="section"><h2>{pair("从四源到站内证据","From four sources to site evidence")}</h2><div class="steps">
<article class="step"><h3>arXiv / GitHub / Hugging Face / Hacker News</h3><p>{pair("按源抓取，统一成 title、URL、来源、发布时间、分数和标签；陌生仓库只读官方材料，不执行代码。","Source adapters normalize title, URL, source, date, score, and tags. Unknown repositories are inspected, never executed.")}</p></article>
<article class="step"><h3>{pair("关键词评分与去重","Scoring and deduplication")}</h3><p>{pair("标题命中加权；既有 URL 先更新再应用新条目上限。同题镜像通过 canonical_id / mirror_of 合并，重试保持幂等。","Title matches receive extra weight. Existing URLs update before the new-item cap. Mirrors use canonical_id / mirror_of; retries stay idempotent.")}</p></article>
<article class="step"><h3>{pair("零模型摘要回填","Model-free abstract backfill")}</h3><p>{pair("GitHub Actions 用摘要生成明确标注的速读，Cursor 缺席时仍可发布；它不计入正文精读历史。","Actions generates a clearly labeled abstract brief, so publishing does not depend on Cursor. It does not count as full-text review.")}</p></article>
<article class="step"><h3>{pair("Cursor 全文精读","Cursor full-text review")}</h3><p>{pair("读取论文正文、官方项目页、仓库和模型页，补问题、方法、流程、结果、局限、开放状态以及对 Harness 的编辑判断。","Cursor reads the paper and official project, repository, and model pages, adding problem, method, workflow, findings, limits, openness, and editorial fit.")}</p></article>
<article class="step"><h3>review_history.json</h3><p>{pair("只有 editorial + fulltext 的状态迁移才入历史；北京时间、来源、详情页和 automation run 可核验。","Only an editorial + fulltext transition enters history, with Beijing time, source, detail route, and automation run.")}</p></article>
</div></section>
<section class="section"><h2>{pair("失败不是静默成功","Failure is not silent success")}</h2><div class="grid">
<article class="card"><h3>{pair("定时","Schedule")}</h3><p>{pair("云端 09:00 / 14:00 / 19:00；本地全文精读建议 02:00 / 15:00 / 20:00 / 23:00。","Cloud at 09:00 / 14:00 / 19:00; local full-text review recommended at 02:00 / 15:00 / 20:00 / 23:00.")}</p></article>
<article class="card"><h3>{pair("重试与锁","Retry and locking")}</h3><p>{pair("本地任务共享原子 PID 锁，可排队六小时；Cursor 调用重试三次且必须输出完成哨兵。","Local tasks share an atomic PID lock and may queue six hours. Cursor retries three times and must emit a completion sentinel.")}</p></article>
<article class="card"><h3>{pair("停止条件","Fail closed")}</h3><p>{pair("锁超时、无哨兵、测试失败、非生成文件冲突或 push 耗尽均返回非零；不会把跳过说成成功。","Lock timeout, missing sentinel, test failure, source conflict, or exhausted push retry returns non-zero; skip is never success.")}</p></article>
</div></section><p><a href="{BASE}/automation/case-hybrid-c/#radar">{pair("案例关联：Radar 建议如何进入 Hybrid C →","Case link: how Radar advice entered Hybrid C →")}</a></p>"""
    return shell("论文调研", "Research", "research", body, snapshot)


def reports(snapshot=None):
    snapshot = snapshot or empty_snapshot()
    body = hero("问题驱动日报", "Problem-driven reports",
        "日报不是“今天有哪些论文”，而是把 Harness 的最新失败、指标和假设，与核验过的外部证据对齐。",
        "The report is not a paper digest. It aligns current Harness failures, metrics, and hypotheses with verified external evidence.",
        '<span class="badge cursor">Cursor synthesis</span><span class="badge script">Scripted publish</span>')
    report_cards = []
    labels = {
        "detail": ("最新详细增量调研", "Latest detailed research"),
        "daily": ("最新每日调研日报", "Latest daily brief"),
    }
    for kind in ("detail", "daily"):
        row = snapshot.get("latest_reports", {}).get(kind)
        if row:
            zh, en = labels[kind]
            report_cards.append(
                f'<article class="card"><h3>{pair(zh,en)}</h3>'
                f'<p><a href="{esc(row["href"])}">{esc(row["date"])} · '
                + pair("打开公开 HTML", "Open public HTML") + "</a></p></article>")
    report_cards.append(
        f'<article class="card"><h3>{pair("报告总天数","Total report days")}</h3>'
        f'<div class="metric"><b>{snapshot.get("report_days", 0)}</b>'
        f'<small>{snapshot.get("report_count", 0)} '
        + pair("份公开报告", "published reports") + "</small></div></article>")
    body += f"""<section class="section"><h2>{pair("当前公开日报","Current published reports")}</h2>
<div class="grid">{"".join(report_cards)}</div>
<p class="callout ok">{pair("内容由 Cursor 结合项目快照与论文证据综合，确定性脚本负责转义、建站、测试和发布。","Cursor synthesizes project snapshots and paper evidence; deterministic scripts handle escaping, site generation, tests, and publishing.")}</p>
<p><a href="{BASE}/reports/">{pair("查看全部报告索引 →","Open all reports →")}</a></p></section>
<section class="section"><h2>{pair("输入、推理、输出","Input, reasoning, output")}</h2><div class="grid">
<article class="card"><h3>{pair("项目快照","Project snapshot")}</h3><ul><li>StreamingModelHarness {pair("最新提交与组件","latest commit and components")}</li><li>{pair("组合准确率、工具执行、端到端 P95","combined accuracy, tool execution, e2e P95")}</li><li>{pair("错误桶、负结果、待验证假设","error buckets, negative results, hypotheses")}</li></ul></article>
<article class="card"><h3>{pair("证据映射","Evidence mapping")}</h3><p>{pair("每个方向写清：当前项目问题→项目证据→相关技术→最小实验→成功门槛。论文数字只能标成论文结果，不能冒充项目实测。","Each direction states project problem→project evidence→related technique→minimum experiment→success gate. Paper numbers remain paper results, never project measurements.")}</p></article>
<article class="card"><h3>{pair("两份日报","Two reports")}</h3><p>{pair("详细增量调研包含 P0/P1/P2、统一技术卡和风险；精简日报每行压缩成“方向（问题；解法；实验）”。","The deep report contains P0/P1/P2, normalized technology cards, and risks. The brief compresses each item to direction (problem; mechanism; experiment).")}</p></article>
</div></section>
<div class="callout"><b>{pair("发布边界：","Publishing boundary:")}</b> {pair("Cursor 任务只改 reports/、project_status/ 和构建后的 docs/；不修改 Harness，不调用 Kimi/Moonshot。测试和构建通过后才由发布脚本提交。","The Cursor task may edit only reports/, project_status/, and generated docs/. It does not modify Harness or call Kimi/Moonshot. Publishing commits only after tests and build pass.")}</div>
<section class="section"><h2>{pair("一次建议如何变成可测问题","How advice becomes a testable question")}</h2>
<div class="decision"><article class="card"><b>{pair("证据","Evidence")}</b><p>Voice Memory / RelayS2S / Qwen-UI-Agent</p></article><div class="arrow">→</div><article class="card"><b>{pair("问题","Question")}</b><p>{pair("能否在不破坏真值和时延的前提下修复确认与 typed action？","Can confirmation and typed actions improve without harming truth or latency?")}</p></article></div>
</section><p><a href="{BASE}/automation/case-hybrid-c/#report">{pair("案例关联：日报建议到 Hybrid C →","Case link: report advice to Hybrid C →")}</a></p>"""
    return shell("问题驱动日报", "Reports", "reports", body, snapshot)


def candidates(snapshot=None):
    snapshot = snapshot or empty_snapshot()
    body = hero("实验候选与隔离实现", "Candidates and isolated implementation",
        "把日报建议拆成一次只改变一个机制的候选。Cursor Agent 可以写代码，但不能改真值、降低阈值或在共享工作树里覆盖别人的实验。",
        "Report advice is decomposed into candidates that change one mechanism at a time. Cursor may write code, but cannot edit truth, lower thresholds, or overwrite another experiment.",
        '<span class="badge cursor">Cursor Agent implementation</span><span class="badge verified">Worktree isolation</span>')
    body += f"""<section class="section"><h2>{pair("候选合同","Candidate contract")}</h2><div class="steps">
<article class="step"><h3>{pair("先写假设","State one hypothesis")}</h3><p>{pair("例：确定性确认可修复确认语句，不改变生成模型；typed resolver 只负责结构化动作消歧。","Example: deterministic confirmation fixes confirmations without changing generation; typed resolver only disambiguates structured actions.")}</p></article>
<article class="step"><h3>{pair("独立 worktree","Isolated worktree")}</h3><p>{pair("每个候选有自己的分支、依赖和运行目录；实现失败可直接丢弃，不污染基线。","Each candidate gets its own branch, dependencies, and runtime directory. A failed implementation can be discarded without contaminating baseline.")}</p></article>
<article class="step"><h3>{pair("保护真值与门槛","Protect truth and gates")}</h3><p>{pair("禁止改测试期望、删除难例、放宽 99% / 1.6s 门槛或用缓存答案伪造命中。","Do not alter expectations, remove hard cases, relax 99% / 1.6s, or fake hits with answer caching.")}</p></article>
<article class="step"><h3>{pair("登记可组合组件","Register composable components")}</h3><p>{pair("Typed Action、Voice Memory、紧凑回执、安全前缀等按组件登记，便于之后组合，而不是把一次实验写成不可拆的补丁。","Typed Action, Voice Memory, compact receipts, and safety prefixes are registered as components for later composition, not one inseparable patch.")}</p></article>
</div></section>
<section class="section"><h2>{pair("为什么强调单变量","Why single-variable candidates")}</h2><p class="callout bad">{pair("多个机制一起变化即使指标上升，也无法知道谁有效；指标下降时更无法安全回退。组合候选只能在各组件已有独立证据后进入。","If several mechanisms change together, neither gains nor regressions are attributable. Combination candidates enter only after each component has independent evidence.")}</p></section>
<p><a href="{BASE}/automation/case-hybrid-c/#candidate">{pair("案例关联：Hybrid C 的六个组件怎样逐步进入 →","Case link: how six Hybrid C components entered →")}</a></p>
<p><a href="{BASE}/automation/limitations/">{pair("证据审计：组合组件如何归因、哪些结论仍不能说 →","Evidence audit: component attribution and claims not yet supported →")}</a></p>"""
    return shell("实验候选", "Candidates", "candidates", body, snapshot)


def h20(snapshot=None):
    snapshot = snapshot or empty_snapshot()
    body = hero("双 GPU H20 隔离评测", "Dual-GPU H20 evaluation",
        "评测把基线与候选放在两个独立 worker，先做便宜的失败筛查，再逐级扩大到真实音频与复杂意图。",
        "Baseline and candidate run in separate workers. Cheap failures are filtered first, then scope expands to real audio and complex intent.",
        '<span class="badge script">Deterministic runner</span><span class="badge pending">First 00:30 unattended run pending</span>')
    body += f"""<section class="section"><h2>{pair("资源拓扑","Resource topology")}</h2><div class="grid">
<article class="card"><h3>Worker A · GPU 4/5</h3><p>{pair("基线或候选 A；188xx 端口段。CUDA 可见设备和服务 PID 明确记录。","Baseline or candidate A; 188xx port range. CUDA visibility and service PIDs are recorded.")}</p></article>
<article class="card"><h3>Worker B · GPU 6/7</h3><p>{pair("候选或复验；189xx 端口段。端口、进程、日志与 worktree 不共享。","Candidate or confirmation; 189xx port range. Ports, processes, logs, and worktree are not shared.")}</p></article>
</div></section>
<section class="section"><h2>{pair("由小到大的评测漏斗","Evaluation funnel")}</h2><div class="steps">
<article class="step"><h3>Smoke</h3><p>{pair("验证服务可启动、协议完整、关键动作能走通；失败立即停止。","Verify startup, protocol integrity, and critical actions; stop immediately on failure.")}</p></article>
<article class="step"><h3>452 {pair("条组合集","combination set")}</h3><p>{pair("覆盖能力组合和回归；同时报告组合完成率与工具执行率，不能用一个数字替代另一个。","Covers capability combinations and regressions. Combined completion and tool execution are reported separately.")}</p></article>
<article class="step"><h3>122 {pair("条复杂意图","complex intents")}</h3><p>{pair("只有前层通过才扩大到多约束、指代、确认与安全边界。","Only survivors expand to multi-constraint, reference, confirmation, and safety cases.")}</p></article>
<article class="step"><h3>pure audio + {pair("真实 ASR","real ASR")}</h3><p>{pair("不把文本直接注入冒充语音结果。音频输入、ASR、模型调用、工具解析和回执均计入真实路径。","Text injection is not presented as speech evaluation. Audio, ASR, model call, tool parse, and receipt remain on the real path.")}</p></article>
</div></section>
<section class="section"><h2>{pair("时延与清理","Latency and cleanup")}</h2><div class="grid">
<article class="card"><h3>e2e P95</h3><p>{pair("从请求进入评测入口到可执行结果/最终回执的端到端尾延迟；call P95 单独报告，不能替代 e2e。","Tail latency from harness ingress to executable result/final receipt. Call P95 is separate and does not replace e2e.")}</p></article>
<article class="card"><h3>{pair("安全清理","Safe cleanup")}</h3><p>{pair("只按启动记录中的 PID 与端口清理；校验归属后终止。禁止模糊匹配杀进程，失败也执行 finally 清理。","Clean only recorded PIDs and ports after ownership checks. No broad process matching; finally cleanup runs after failures.")}</p></article>
</div></section>
<div class="callout"><b>{pair("证据声明：","Evidence statement:")}</b> {pair("该隔离方案和手动案例数据可核验；“每天 00:30 已稳定无人值守运行”尚不能声称，首次定时实跑仍待验证。","The isolation design and manual case data are verifiable. Stable daily unattended 00:30 operation is not claimed; the first scheduled run remains pending.")}</div>
<p><a href="{BASE}/automation/case-hybrid-c/#evaluation">{pair("案例关联：B 的 452 基线与 Hybrid C 的 4 条 smoke →","Case link: B's 452 baseline and Hybrid C's four-case smoke →")}</a></p>
<p><a href="{BASE}/automation/limitations/">{pair("查看评测集、指标口径与统计有效性缺口 →","Audit evaluation-set, metric, and statistical-validity gaps →")}</a></p>"""
    return shell("H20 隔离评测", "H20 evaluation", "h20", body, snapshot)


def selection(snapshot=None):
    snapshot = snapshot or empty_snapshot()
    body = hero("选择、Pareto 与局部留存", "Selection, Pareto, and partial retention",
        "选择器不是挑一个好看的总分，而是依次验口径、过安全门、与同口径基线比较，再决定保留整套候选、只保留可归因组件，还是记录负结果。",
        "Selection does not pick the prettiest aggregate score. It validates scope, applies safety gates, compares a like-for-like baseline, then retains a whole candidate, only attributable components, or a negative result.",
        '<span class="badge script">Deterministic gates</span><span class="badge fact">strict execution ≥99%</span><span class="badge fact">e2e P95 ≤1600ms</span>')
    registry = ("https://github.com/ISS-2030Lab/StreamingModelHarness/blob/"
                "automation/agent-h20-loop/evolution/experiments/registry.json")
    retained_json = ("https://github.com/ISS-2030Lab/StreamingModelHarness/blob/"
                     "automation/agent-h20-loop/evolution/retained_components.json")
    retained_md = ("https://github.com/ISS-2030Lab/StreamingModelHarness/blob/"
                   "automation/agent-h20-loop/evolution/RETAINED_COMPONENTS.md")
    body += f"""<section class="section"><h2>{pair("先用验车比喻说清楚","First, a vehicle-inspection analogy")}</h2>
<div class="card plain-analogy"><p>{pair("像验收一辆改装车：先确认考卷没泄题、传感器和计时器都正常；再确认不会危险误控；然后拿同一条赛道、同一批样本和原车比成绩；最后才决定整车可入选，还是只拆下某个有独立证据的零部件保留。",
"Think of accepting a modified car: first verify the exam was not leaked and the sensors and timers worked; next prove it did not make dangerous controls; then compare it with the original car on the same track and samples; only then accept the whole car or retain a component backed by independent evidence.")}</p>
<ol><li>{pair("先验卷：有效性与口径。","Validate the exam: evidence and scope.")}</li>
<li>{pair("再判安全：危险误控、闲聊误控与候选授权。","Check safety: dangerous/chat miscalls and candidate authorization.")}</li>
<li>{pair("再比成绩：完成、严格执行、时延、复杂集和相对基线。","Compare results: completion, strict execution, latency, complex suite, and baseline delta.")}</li>
<li>{pair("最后定留存粒度：整套方案或可归因零部件。","Choose retention granularity: whole candidate or attributable component.")}</li></ol></div></section>

<section class="section"><h2>{pair("严格定义：两层资格","Strict definition: two eligibility tiers")}</h2><div class="grid">
<article class="card verdict warn"><h3>research_eligible</h3><p>{pair("研究可比，不等于可生产。源码要求 pure_audio + full stage、smoke/regression 通过、至少 452 条、完成率≥99%、实际执行证据覆盖100%、严格 expected-tool 实际执行≥99%、危险误控=0、闲聊误控≤1%且有闲聊样本、commit→首音频 e2e P95≤1600ms、复杂集成功≥95%、同口径基线不退化，并覆盖 clean/noisy、single/multi-turn、L0/L1 和至少两种音色。",
"Research-comparable, not production-ready. Source requires pure_audio full stage, smoke/regression pass, at least 452 samples, completion ≥99%, 100% actual-execution evidence coverage, strict expected-tool actual execution ≥99%, zero dangerous miscalls, chat miscalls ≤1% with chat samples, commit-to-first-audio e2e P95 ≤1600ms, complex-suite success ≥95%, no regression against a like-for-like baseline, plus clean/noisy, single/multi-turn, L0/L1, and at least two voices.")}</p></article>
<article class="card verdict good"><h3>production_eligible</h3><p>{pair("先满足 research_eligible，再要求每个任务样本的参数 + 最终车态真值覆盖率=100%，且有真值样本上的语义任务成功率≥99%。这是“做对了什么并让车达到正确状态”，不是只命中工具名。",
"Requires research_eligible first, then 100% parameter + final-state truth coverage for task samples and semantic task success ≥99% on truth-covered samples. This means the right action reached the right vehicle state, not merely the right tool name.")}</p></article>
</div>
<p class="callout"><b>{pair("源码核对后的缺口：","Source-audited gaps:")}</b> {pair("当前默认 commit_to_call P95 门为 None，真正启用时才成为 research 硬门；评分源码已有参数/最终态 production 门，但历史 452 registry 只有工具执行代理指标、复杂集 not_run，且 2 条基础设施错误仍在记录中，因此历史组合不能补写成 eligible。",
"The default commit_to_call P95 target is None and becomes a research gate only when configured. Scoring source already has production parameter/final-state gates, but the historical 452 registry contains only a tool-execution proxy, complex suite not_run, and two recorded infrastructure errors; it cannot be rewritten as eligible.")}</p></section>

<section class="section"><h2>{pair("可交互决策树","Interactive decision tree")}</h2>
<p class="sub">{pair("点击或用 Tab 聚焦后按 Enter/Space 展开每道门；原生 details 控件无需脚本，减少动态效果设置同样生效。","Click, or focus with Tab and press Enter/Space, to expand each gate. Native details need no script and respect reduced-motion settings.")}</p>
<div class="decision-tree" role="tree" aria-label="候选选择决策树 Candidate selection decision tree">
<details role="treeitem"><summary tabindex="0">{pair("基础设施与口径有效？否 → invalid","Infrastructure and scope valid? No → invalid")}</summary><p>{pair("输入：profile、stage、manifest audit、sample_id 映射、unknown ID、音频来源、服务/端口/GPU/TTS 错误、结果文件与哈希。pure_audio 禁止 assisted_text、manifest 原文或 truth_text_preinjected 捷径。","Inputs: profile, stage, manifest audit, sample-ID mapping, unknown IDs, audio provenance, service/port/GPU/TTS errors, result files, and hashes. pure_audio forbids assisted_text, manifest transcript, or truth_text_preinjected shortcuts.")}</p></details>
<details role="treeitem"><summary tabindex="0">{pair("安全门通过？否 → rejected","Safety gate passes? No → rejected")}</summary><p>{pair("输入：dangerous_miscalls=0、chit_chat_miscall_rate≤1%、闲聊样本存在、每个 call 在候选授权集合内、真实执行证据存在。口径无效优先 invalid；有效但安全退化才 rejected。","Inputs: dangerous_miscalls=0, chit_chat_miscall_rate≤1%, chat samples present, every call within candidate authorization, and real execution evidence. Invalid scope takes precedence; valid evidence with a safety regression is rejected.")}</p></details>
<details role="treeitem"><summary tabindex="0">{pair("相对同口径基线有收益？否 → rejected","Benefit over like-for-like baseline? No → rejected")}</summary><p>{pair("输入：baseline_id、profile、样本/分桶、完成率、actual_execution_success_rate、e2e P95 与 delta。样本范围不同、映射无效或必需指标缺失时不是“无收益”，而是 invalid。","Inputs: baseline_id, profile, sample/buckets, completion, actual_execution_success_rate, e2e P95, and delta. Different scope, invalid mapping, or missing required metrics means invalid, not “no gain.”")}</p></details>
<details role="treeitem"><summary tabindex="0">{pair("全部研究/生产硬门通过？是 → qualified","All research/production hard gates pass? Yes → qualified")}</summary><p>{pair("输入：smoke、full≥452、分桶、完成、安全、严格执行、e2e、复杂集、基线不退化；生产层再读 truth_coverage 与 task_success_rate。qualified 必须注明是 research 还是 production 资格。","Inputs: smoke, full≥452, buckets, completion, safety, strict execution, e2e, complex suite, and no baseline regression; production additionally reads truth_coverage and task_success_rate. qualified must state whether it is research or production eligibility.")}</p></details>
<details role="treeitem"><summary tabindex="0">{pair("未过全部门但有收益？→ pareto 或 partial_improvement","Some gain but not all gates? → pareto or partial_improvement")}</summary><p>{pair("当前 registry.classify_result 对未 qualified 且安全、可比、有质量/时延收益的候选分类：若位于前沿则 pareto，否则 partial_improvement。二者都不是 production eligible；只有可归因组件才能进入 retained/conditional。",
"Current registry.classify_result labels a non-qualified but safe, comparable candidate with quality/latency gain as pareto when on the frontier, otherwise partial_improvement. Neither is production eligible; only attributable components may become retained/conditional.")}</p></details>
<div class="tree-outcomes" role="group" aria-label="Decision outcomes"><span class="badge verified">qualified</span><span class="badge pending">pareto</span><span class="badge pending">partial_improvement</span><span class="badge bad">rejected</span><span class="badge bad">invalid</span></div></div></section>

<section class="section"><h2>{pair("五类状态：代码与发布含义","Five statuses: code and publishing semantics")}</h2>
<table class="evidence-table"><thead><tr><th>Status</th><th>{pair("必要条件 / 常见原因","Requirements / common causes")}</th><th>{pair("GitHub 分支","GitHub branch")}</th><th>{pair("默认组合","Default composition")}</th><th>{pair("允许的文档措辞","Allowed wording")}</th></tr></thead><tbody>
<tr><td><b class="verified">qualified</b></td><td>{pair("对应资格层全部硬门通过；必须注明 research 或 production。","All gates for the named tier pass; state research or production.")}</td><td>{pair("保留并归档","Retain and archive")}</td><td>{pair("仍需人工合并决策；production 才可谈部署","Still requires human merge decision; only production may be discussed for deployment")}</td><td>{pair("“在所列范围通过全部门”","“Passed all gates for the stated scope”")}</td></tr>
<tr><td><b class="pending">pareto</b></td><td>{pair("安全、可比、有收益但未 qualified，且在准确率高/时延低二维不被另一候选支配。","Safe, comparable, beneficial but not qualified, and non-dominated on higher accuracy/lower latency.")}</td><td>{pair("保留实验分支","Retain experiment branch")}</td><td>{pair("否；仅供研究前沿比较","No; research-frontier comparison only")}</td><td>{pair("“未过全部门的非支配局部候选”","“Non-dominated scoped candidate that missed full gates”")}</td></tr>
<tr><td><b class="pending">partial_improvement</b></td><td>{pair("安全、可比，至少一项质量提升或时延下降，但整体门失败或证据范围不足。","Safe and comparable with at least one quality or latency gain, but full gates fail or scope is insufficient.")}</td><td>{pair("自动保留实验分支","Experiment branch retained automatically")}</td><td>{pair("整套否；组件须有归因证据才 retained/conditional","Whole candidate: no; components require attributable evidence for retained/conditional")}</td><td>{pair("“仅在 X 范围有局部收益”","“Scoped gain only on X”")}</td></tr>
<tr><td><b class="bad">rejected</b></td><td>{pair("有效证据显示无收益、退化、安全失败或被更简单方案支配；如工具描述增强 0/31。","Valid evidence shows no gain, regression, safety failure, or domination; e.g. tool-description enhancement 0/31.")}</td><td>{pair("默认不推；仅显式 push_rejected 时留负结果分支","Not pushed by default; negative branch only with push_rejected")}</td><td>{pair("否","No")}</td><td>{pair("“已测试无收益/退化，记录避免重复”","“Tested with no gain/regression; recorded to avoid repetition”")}</td></tr>
<tr><td><b class="bad">invalid</b></td><td>{pair("基础设施失败、口径不可比、映射失效、真值捷径或证据缺失，不能比较。","Infrastructure failure, incomparable scope, invalid mapping, truth shortcut, or missing evidence prevents comparison.")}</td><td>{pair("不作为结果分支发布","Not published as a result branch")}</td><td>{pair("否","No")}</td><td>{pair("“本次无有效结论，必须重跑”","“No valid conclusion; rerun required”")}</td></tr>
</tbody></table>
<div class="callout"><b>Pareto {pair("例子：","example:")}</b> {pair("候选 A 准确率 99.2%、e2e 1500ms；B 为 99.0%、1300ms：A 更准、B 更快，互不支配。若 C 为 99.0%、1500ms，则 A 准确率更高且时延相同，C 被 A 支配，不在前沿。",
"Candidate A has 99.2% accuracy at 1500ms; B has 99.0% at 1300ms. A is more accurate and B faster, so neither dominates. If C is 99.0% at 1500ms, A has higher accuracy at equal latency and dominates C.")}</div></section>

<section class="section"><h2>{pair("逐门口径说明","Gate-by-gate definitions")}</h2>
<div class="grid">
<article class="card"><h3>validity</h3><p>{pair("必须是真实音频路径；pure_audio 禁止读 manifest 原文、辅助文本或预注入真值。sample_id 必须映射到已知样本，unknown ID、缺日志、服务/TTS/GPU 故障与不完整结果要 fail closed。","Must use the real audio path. pure_audio forbids manifest transcripts, assisted text, or pre-injected truth. sample_id must map to known data; unknown IDs, missing logs, service/TTS/GPU faults, or incomplete results fail closed.")}</p></article>
<article class="card"><h3>safety</h3><p>{pair("危险误控必须为 0；闲聊误控率≤1%且分母必须含真实闲聊样本；所有工具调用必须在候选授权集合内，并有实际执行证据。","Dangerous miscalls must be zero; chat miscalls ≤1% with real chat samples in the denominator; every call must be candidate-authorized and backed by actual-execution evidence.")}</p></article>
<article class="card"><h3>completion</h3><p>{pair("完成率=产生有效终止结果的样本数/全部入场样本，超时与基础设施错误不能从分母静默删除。452 组的 99.56% 即约 450/452，不等于工具执行正确。","Completion is valid terminal outcomes divided by all admitted samples; timeouts and infrastructure errors cannot silently leave the denominator. 99.56% on 452 is about 450/452 and is not tool-execution correctness.")}</p></article>
<article class="card"><h3>accuracy / truth</h3><p>{pair("research 严格执行要求 expected tool 与真实 call 对齐，且 execution evidence 覆盖100%；production 再要求参数合法、期望最终态与实际最终态一致。routing、工具名、参数、最终态必须分列，不能都叫“准确率”。","Research strict execution aligns expected tool with a real call and requires 100% execution-evidence coverage. Production adds legal parameters and expected-versus-actual final state. Routing, tool name, parameters, and final state must stay separate, not all be called “accuracy.”")}</p></article>
<article class="card"><h3>latency</h3><p>{pair("e2e 是 commit→首音频 P95；call P95 单列。Relay 安全前缀可能使首音频≤1600ms，但真实 call 仍慢。约 0.7s VAD 静音窗不在该 e2e 内，必须另报。","e2e is commit-to-first-audio P95; call P95 is separate. A Relay safety prefix may put first audio under 1600ms while the real call remains slow. The roughly 0.7s VAD silence window is outside this e2e and must be reported separately.")}</p></article>
<article class="card"><h3>complex / multiturn</h3><p>{pair("research 需要 122 复杂意图套件结果，默认目标≥95%，并覆盖 single_turn/multi_turn。合成复杂集只能补结构难度，不能替代真实车内分布。","Research requires the 122-case complex-intent result with default target ≥95% and both single_turn/multi_turn buckets. A synthetic complex suite adds structural difficulty but does not replace real in-car distribution.")}</p></article>
<article class="card"><h3>baseline / delta</h3><p>{pair("基线必须 mapping_valid、profile 一致、包含完成/实际执行/e2e 必需指标，并在相同样本与分桶比较；任何完成、严格执行或 e2e 退化都会阻断资格。多 seed 和置信区间尚未成为当前源码硬门，是明确待补缺口。","Baseline must be mapping_valid, profile-matched, include completion/actual-execution/e2e metrics, and use the same samples and buckets. Regression in completion, strict execution, or e2e blocks eligibility. Multiple seeds and confidence intervals are not yet source hard gates and remain explicit gaps.")}</p></article>
</div></section>

<section class="section"><h2>{pair("整套方案留存 vs 子组件留存","Whole-candidate vs component retention")}</h2>
<div class="grid"><article class="card"><h3>{pair("整套候选","Whole candidate")}</h3><p>{pair("只有明确资格层的全部硬门通过，才可写 qualified。pareto/partial 的实验分支用于复现和消融，不自动进默认组合、不合并 main。","Only passing every gate for a named tier permits qualified. Pareto/partial experiment branches exist for reproduction and ablation; they do not enter the default composition or merge main automatically.")}</p></article>
<article class="card"><h3>{pair("可归因子组件","Attributable component")}</h3><p>{pair("组合未过门时，组件只有在单测、微基准、消融或明确局部错误桶能归因时才可标 retained/conditional。组合共享 e2e 不能拆给每个组件；无收益组件保持 rejected。","When a combination fails, a component becomes retained/conditional only with attributable unit, microbenchmark, ablation, or scoped-bucket evidence. Shared combination e2e cannot be assigned to each component; no-gain components remain rejected.")}</p></article></div>
<div class="legend"><a class="btn" href="{retained_json}">retained_components.json</a><a class="btn" href="{retained_md}">RETAINED_COMPONENTS.md</a><a class="btn" href="{registry}">experiment registry.json</a></div></section>

<section class="section"><h2>{pair("当前三张判定卡","Three current verdict cards")}</h2><div class="grid">
<article class="card verdict warn"><h3>B pure-audio · 452 · partial_improvement</h3><div class="metrics"><div class="metric"><b>99.56%</b><small>completion</small></div><div class="metric"><b>81.64%</b><small>actual tool execution</small></div><div class="metric"><b>1241.6ms</b><small>e2e P95</small></div><div class="metric"><b>1818.7ms</b><small>call P95</small></div></div><p>{pair("2 条 infrastructure errors；Relay 首响让 e2e 时延门通过，但严格工具执行远低于 99%，复杂集 not_run。registry 结论是 partial_improvement，不是 qualified。","Two infrastructure errors. Relay first audio passes the e2e latency gate, but strict tool execution is far below 99% and the complex suite is not_run. Registry verdict: partial_improvement, not qualified.")}</p><a href="{registry}">{pair("查看 registry 原记录","Open source registry record")}</a></article>
<article class="card verdict warn"><h3>Hybrid C · 4-case smoke · partial_improvement</h3><div class="metrics"><div class="metric"><b>4 / 4</b><small>smoke only</small></div><div class="metric"><b>1195ms</b><small>e2e</small></div><div class="metric"><b>975.2ms</b><small>call</small></div></div><p>{pair("证明该小路径能工作；与 452 样本范围不可比，无复杂集、分桶或置信区间，不能 full qualified。若拿它做全量结论，证据范围即 invalid。","Shows this small path can work. It is incomparable with the 452 scope and lacks complex-suite, buckets, and confidence intervals, so it cannot be fully qualified. Using it for a full-scope claim would make the evidence invalid.")}</p><a href="https://github.com/ISS-2030Lab/StreamingModelHarness/tree/experiment/20260805-hybrid-c-asr-smoke">{pair("查看实验分支","Open experiment branch")}</a></article>
<article class="card verdict bad"><h3>{pair("工具描述增强 · 31 条 · rejected","Tool-description enhancement · 31 cases · rejected")}</h3><div class="metric"><b>0 / 31</b><small>{pair("修复","fixed")}</small></div><p>{pair("有效错误桶测试没有修复任何一条，无准确率收益；保留 registry 负结果避免重复，不进入默认组合。","A valid error-bucket test fixed none and showed no accuracy gain. Keep the negative registry record to prevent repetition; do not enter the default composition.")}</p><a href="{registry}">{pair("查看负结果记录","Open negative record")}</a></article>
</div></section>

<section class="section"><h2>{pair("常见误读 FAQ","Common misreadings FAQ")}</h2>
<details><summary>{pair("P95 是平均值吗？","Is P95 an average?")}</summary><p>{pair("不是。P95 是至少 95% 样本不超过的尾延迟位置；仍需同时看样本数、失败样本和更高分位。","No. P95 is a tail position under which at least 95% of samples fall; sample count, failed samples, and higher tails still matter.")}</p></details>
<details><summary>{pair("4/4 能写成 99% 吗？","Can 4/4 be called 99%?")}</summary><p>{pair("不能。4 条只是一组冒烟，无法支撑总体比例或窄置信区间。","No. Four cases are a smoke set and cannot establish a population rate or narrow confidence interval.")}</p></details>
<details><summary>{pair("首音频出来代表车已经动了吗？","Does first audio mean the car moved?")}</summary><p>{pair("不代表。Relay 可先播非承诺前缀；真实 call、执行回执和最终车态可能在后面。","No. Relay may play a non-committal prefix first; the real call, execution receipt, and final state may happen later.")}</p></details>
<details><summary>{pair("工具名对了，参数也一定对吗？","Does the right tool name imply right parameters?")}</summary><p>{pair("不一定。工具名、参数合法性、动作顺序和最终车态是不同真值层。","No. Tool name, parameter legality, action order, and final state are distinct truth layers.")}</p></details>
<details><summary>partial_improvement {pair("可以生产吗？","production-ready?")}</summary><p>{pair("不可以。partial 只说明某范围或组件有收益；必须补齐 research/production 全部门和明确归因。","No. Partial means scoped or component-level gain only; all research/production gates and attribution remain required.")}</p></details></section>

<div class="legend"><a class="btn" href="{BASE}/automation/candidates/">{pair("候选页","Candidates")}</a><a class="btn" href="{BASE}/automation/h20/">{pair("H20 评测","H20 evaluation")}</a><a class="btn" href="{BASE}/automation/limitations/">{pair("局限审计","Limitations audit")}</a><a class="btn" href="{BASE}/automation/case-hybrid-c/#decision">{pair("Hybrid C 判定","Hybrid C verdict")}</a></div>"""
    return shell("选择与留存", "Selection", "selection", body, snapshot)


def publishing(snapshot=None):
    snapshot = snapshot or empty_snapshot()
    body = hero("发布、验收与反馈", "Publishing, verification, and feedback",
        "实验代码、结果 registry 与公开讲解分别发布，但都必须指向同一组可核验证据；发布成功以远端和 Pages 验收为准。",
        "Experiment code, result registry, and public explanation publish separately but point to the same evidence. Success requires remote and Pages verification.",
        '<span class="badge script">Git + Pages scripted</span><span class="badge verified">Site smoke verified</span>')
    body += f"""<section class="section"><h2>{pair("发布链","Publishing chain")}</h2><div class="steps">
<article class="step"><h3>{pair("实验分支","Experiment branch")}</h3><p>{pair("候选提交到 GitHub experiment 分支，不直接把未过门改动并入主线；提交记录关联候选 ID。","Candidates publish to GitHub experiment branches; gate failures do not merge into the main implementation. Commits reference candidate IDs.")}</p></article>
<article class="step"><h3>registry + retained components</h3><p>{pair("记录配置、提交、数据范围、指标、状态、错误桶和负结果；partial 只登记被保留的组件与适用边界。","Record config, commit, scope, metrics, status, error buckets, and negative results. Partial entries name only retained components and boundaries.")}</p></article>
<article class="step"><h3>{pair("网站与 Pages 验收","Website and Pages verification")}</h3><p>{pair("生成 docs 后测试互链和关键事实，push main；Pages smoke 有限重试检查首页、存档、RSS、日报、演示及自动化路由。","After link and fact tests, generate docs and push main. Bounded Pages smoke checks home, archive, RSS, reports, demos, and automation routes.")}</p></article>
<article class="step"><h3>{pair("本地同步与反馈","Local sync and feedback")}</h3><p>{pair("发布克隆安全 fetch/rebase；生成文件冲突重建，源数据冲突 fail closed。registry 中的成功、partial 和负结果都进入下一份项目快照与日报。","The publisher clone fetches/rebases safely. Generated conflicts rebuild; source conflicts fail closed. Successes, partials, and negatives all feed the next snapshot and report.")}</p></article>
</div></section>
<div class="callout ok"><b>{pair("闭环的关键：","What closes the loop:")}</b> {pair("下一日报不仅看新论文，也读取上一轮“哪里失败、哪个错误桶缩小、哪个组件值得组合”，因此不会每天从零开始。","The next report reads not only new papers but previous failures, reduced error buckets, and composable components, so each day does not restart from zero.")}</div>
<p><a href="{BASE}/automation/case-hybrid-c/#publish">{pair("案例关联：Hybrid C 的分范围结论如何发布 →","Case link: publishing Hybrid C's scoped conclusion →")}</a></p>"""
    return shell("发布与反馈", "Publishing", "publishing", body, snapshot)


def limitations(snapshot=None):
    snapshot = snapshot or empty_snapshot()
    body = hero(
        "局限与证据审计", "Limitations and evidence audit",
        "这是系统自我批评页，不是宣传页：它把可比基线、论文到代码的证据链、评测盲区和允许作出 99% 声明的条件放在同一处。",
        "This is a system self-critique, not a marketing page. It puts comparable baselines, paper-to-code provenance, evaluation blind spots, and the gate for any 99% claim in one place.",
        '<span class="badge mixed">Audit view</span><span class="badge pending">Evidence gaps visible</span>')
    body += f"""<section class="section"><div class="audit-banner"><b>{pair("审计结论：","Audit conclusion:")}</b>
{pair("当前自动进化不是“从 A 单线改到 C”。A 与 B 都保留；452 条同口径可比结果属于 B pure-audio 组合，而 Hybrid C 只有 4 条常规冒烟和 31 条错误桶的局部证据，尚无同口径 452 全量结果。",
"The current evolution is not a single A-to-C rewrite. A and B are both retained. The comparable 452-case result belongs to the B pure-audio combination; Hybrid C has only a four-case routine smoke and scoped evidence on a 31-case error bucket, not a like-for-like 452-case run.")}</div></section>

<section class="section"><h2>{pair("A / B / Hybrid C 基线关系","A / B / Hybrid C baseline relationship")}</h2>
<div class="compare">
<article class="card"><h3>A · ASR / RAG</h3><p>{pair("真实 ASR 后做 RAG 候选召回与晚注入；其预取思想进入 C，但 A 本身仍作为独立基线保留。","Real ASR followed by RAG candidate recall and late injection. Its prefetch path informs C, while A remains an independent baseline.")}</p></article>
<article class="card"><h3>B · pure audio · 452</h3><p>{pair("Qwen 直听音频，组合 grouped MoE、紧凑回执、确定性确认与 Relay 安全前缀。99.56% 组合完成率、81.64% 工具执行率和 1241.6ms e2e P95 属于这个 B 组合。","Qwen hears audio directly and combines grouped MoE, compact receipts, deterministic confirmation, and a Relay safety prefix. The 99.56% combined completion, 81.64% tool execution, and 1241.6ms e2e P95 belong to this B combination.")}</p></article>
<article class="card"><h3>Hybrid C · scoped only</h3><p>{pair("组合 A 的真实 ASR/RAG 预取与 B 的直听音频、回执和 typed action。当前只有 4/4 常规冒烟及错误桶 24/31 的局部修复，不能外推到 452。",
"Combines A's real-ASR/RAG prefetch with B's direct audio, receipts, and typed actions. Evidence is limited to a 4/4 routine smoke and a 24/31 scoped error-bucket repair; neither extrapolates to 452.")}</p></article>
</div>
<p class="callout bad">{pair("禁止表述：“Hybrid C 在 452 条上达到 99.56%”或“Hybrid C 已达到 99%”。前者把 B 的结果错挂到 C，后者把 4 条冒烟或错误桶修复外推为总体准确率。",
"Prohibited claims: “Hybrid C reached 99.56% on 452 cases” or “Hybrid C has reached 99%.” The first assigns B's result to C; the second extrapolates a four-case smoke or an error-bucket repair into overall accuracy.")}</p></section>

<section class="section"><h2>{pair("论文如何映射到候选，而不是变成宣传引用","How papers map to candidates without becoming marketing citations")}</h2>
<p>{pair("候选 manifest 记录 candidate_id、基线、单一假设、source_paths 和 success gates；experiment registry 记录提交、数据范围、指标与负结果；retained components 只登记有独立局部证据的组件及边界。日报和论文链接必须进入 evidence，不能只留在说明文字。",
"A candidate manifest records candidate_id, baseline, one hypothesis, source_paths, and success gates. The experiment registry records commit, data scope, metrics, and negative results. Retained components name only components with independent scoped evidence and their boundaries. Report and paper links belong in evidence, not only prose.")}</p>
<div class="card"><code>source_paths: [reports/每日调研日报-YYYY-MM-DD.md, data/review_history.json, docs/items/&lt;id&gt;.html]</code><br>
<code>evidence: [paper URL, site review, baseline run, candidate run, error buckets]</code></div>
<table class="evidence-table"><thead><tr><th>{pair("工程组件","Engineering component")}</th><th>{pair("真实论文证据","Real paper evidence")}</th><th>{pair("允许的工程判断","Permitted engineering inference")}</th></tr></thead><tbody>
<tr><td>{pair("Relay 安全前缀","Relay safety prefix")}</td><td><a href="{BASE}/items/5e1773f2f1.html">RelayS2S · {pair("站内精读","site review")}</a><br><a href="https://arxiv.org/abs/2603.23346v1" rel="noopener noreferrer">{pair("原论文","paper")}</a></td><td>{pair("借鉴双路前缀与 verifier，把前缀限制为不承诺事实的安全回执；论文没有证明该 Harness 的车控安全或工具正确率。","Borrow dual-path prefixing and verification, restricting the prefix to a non-committal safety receipt. The paper does not prove this Harness's vehicle-control safety or tool correctness.")}</td></tr>
<tr><td>{pair("可审计 ASR 纠错","Auditable ASR correction")}</td><td><a href="{BASE}/items/3bebe83725.html">Voice Memory · {pair("站内精读","site review")}</a><br><a href="https://arxiv.org/abs/2607.26410v1" rel="noopener noreferrer">{pair("原论文","paper")}</a></td><td>{pair("借鉴保留集门控、可回滚 memory 和 abstain；论文结果不是车载口音、噪声或 Harness 最终车态结果。","Borrow held-out gating, reversible memory, and abstention. Paper results are not in-car accent/noise or Harness final-state results.")}</td></tr>
<tr><td>typed action / {pair("工具轨迹","tool trajectories")}</td><td><a href="{BASE}/items/c8d10ef1c8.html">Qwen-UI-Agent · {pair("站内精读","site review")}</a> · <a href="https://huggingface.co/papers/2607.28227" rel="noopener noreferrer">{pair("原论文","paper")}</a><br><a href="{BASE}/items/386ec68e80.html">SpeechAgent-R · {pair("站内精读","site review")}</a> · <a href="https://arxiv.org/abs/2608.01881v1" rel="noopener noreferrer">{pair("原论文","paper")}</a></td><td>{pair("借鉴统一 action schema、工具交互轨迹和过程评测；GUI/声学工具任务并不直接证明座舱车控 typed action 成功。","Borrow unified action schemas, tool-interaction trajectories, and process evaluation. GUI and acoustic-tool tasks do not directly prove cockpit typed-action success.")}</td></tr>
<tr><td>POLAR / {pair("前端诊断证据","front-end diagnostic evidence")}</td><td><a href="{BASE}/items/f474b60b71.html">POLAR · {pair("站内精读","site review")}</a><br><a href="https://arxiv.org/abs/2607.11157v1" rel="noopener noreferrer">{pair("原论文","paper")}</a></td><td>{pair("POLAR 诊断增强对 ASR 的幅度/相位影响，可进入 source_paths 和前端反事实实验；它不提出 typed action 或工具轨迹，不能被误写成工具调用证据。","POLAR diagnoses magnitude/phase effects of enhancement on ASR and can inform source_paths and front-end counterfactuals. It does not propose typed actions or tool trajectories and must not be cited as tool-calling evidence.")}</td></tr>
</tbody></table>
<p class="callout">{pair("工程组合是本项目的编辑判断与实验假设，不是上述论文的原结论。每个论文结果、项目实测和待验证门槛必须分栏记录。",
"The engineering combination is this project's editorial judgment and experimental hypothesis, not an original conclusion of any cited paper. Paper results, project measurements, and pending gates must remain separate.")}</p></section>

<section class="section"><h2>{pair("评测集缺口","Evaluation-set gaps")}</h2>
<p>{pair("452 条主要覆盖四个 L0/L1 设置与车控集合，偏单轮、干净、有限且近似单音色。122 条复杂意图是合成补充，能增加结构难度，但不能替代真实分布。",
"The 452 cases mainly cover four L0/L1 settings and a vehicle-control set; they skew single-turn, clean, and limited or effectively single-voice. The 122 complex intents are synthetic supplements, not substitutes for the real distribution.")}</p>
<div class="risk-grid">
<article class="card risk high"><h3>{pair("声学与多人","Acoustics and speakers")}</h3><p>{pair("多音色/口音、20dB 及更强噪声、AEC 双讲、多人受话对象覆盖不足。","Insufficient voices/accents, 20dB and stronger noise, AEC double-talk, and addressee selection.")}</p></article>
<article class="card risk high"><h3>{pair("自然交互","Natural interaction")}</h3><p>{pair("自然 VAD、句中停顿、附和、打断、连续多轮 KV 和改口不足。","Natural VAD, within-utterance pauses, backchannels, interruptions, continuous multi-turn KV, and corrections are under-covered.")}</p></article>
<article class="card risk high"><h3>{pair("安全与真值","Safety and ground truth")}</h3><p>{pair("闲聊误车控、危险动作、参数正确与最终车态 100% 真值尚未形成完整合同。","No complete contract yet for chat-triggered controls, dangerous actions, parameter correctness, and 100% final vehicle-state truth.")}</p></article>
<article class="card risk medium"><h3>{pair("部署分布","Deployment distribution")}</h3><p>{pair("缺少真实车载麦克风、扬声器、硬件抖动、网络波动、移动说话人与长时间会话回放。","Missing real in-car microphones/speakers, hardware jitter, network variation, moving speakers, and long-session replay.")}</p></article>
<article class="card risk medium"><h3>{pair("统计有效性","Statistical validity")}</h3><p>{pair("未系统报告分桶置信区间、重复 seed、holdout 和最差条件。并行 GPU 只缩短墙钟时间，不增加样本独立性。","No systematic bucketed confidence intervals, repeated seeds, holdout, or worst-condition reporting. Parallel GPUs reduce wall time, not statistical validity.")}</p></article>
</div>
<details><summary>{pair("展开完整缺口清单","Expand the complete gap checklist")}</summary>
<ul><li>{pair("多音色、方言和口音；clean、20dB、5dB 或更强噪声分桶。","Multiple voices, dialects, and accents; clean, 20dB, 5dB or stronger noise buckets.")}</li>
<li>{pair("AEC 残留、系统播放期间双讲、主驾/副驾/后排受话对象。","AEC residue, double-talk during playback, and driver/passenger/rear-seat addressee.")}</li>
<li>{pair("自然判停、停顿、附和、抢话、打断恢复与连续多轮 KV。","Natural endpointing, pauses, backchannels, overlap, interruption recovery, and continuous multi-turn KV.")}</li>
<li>{pair("闲聊 no-op、危险动作拒绝、参数、动作顺序、幂等、执行回执和最终车态。","Chat no-op, dangerous-action refusal, parameters, action order, idempotency, execution receipt, and final vehicle state.")}</li>
<li>{pair("真实车载硬件/网络回放、冻结 holdout、重复 seed 与置信区间。","Real in-car hardware/network replay, frozen holdout, repeated seeds, and confidence intervals.")}</li></ul></details></section>

<section class="section"><h2>{pair("指标与流程风险矩阵","Metric and process risk matrix")}</h2>
<div class="risk-grid">
<article class="card risk high"><h3>e2e {pair("口径","scope")}</h3><p>{pair("当前 e2e 从 commit 到首音频，不含约 0.7s VAD 窗；不得与用户开始说话到首响混用。Relay 前缀可让首响过门，但后续 call 仍可能慢。","Current e2e runs from commit to first audio and excludes the roughly 0.7s VAD window. It is not user-speech-start to first response. A Relay prefix may pass first-response latency while the later call remains slow.")}</p></article>
<article class="card risk high"><h3>{pair("正确性代理指标","Correctness proxies")}</h3><p>{pair("工具名命中不等于参数、执行顺序或最终车态成功；4/4 与 24/31 也都不能称为 99%。","A tool-name hit is not parameter, execution-order, or final-state success. Neither 4/4 nor 24/31 may be called 99%.")}</p></article>
<article class="card risk medium"><h3>{pair("选择与归因","Selection and attribution")}</h3><p>{pair("日报到代码存在选择偏差；单变量要求与多组件组合的归因冲突，必须补消融和反事实对照。","Report-to-code selection can be biased. Single-variable requirements conflict with multi-component attribution, requiring ablations and counterfactual controls.")}</p></article>
<article class="card risk high"><h3>{pair("错误桶过拟合","Error-bucket overfit")}</h3><p>{pair("规则针对 31 条错误桶可能只记住局部模式；必须在冻结 holdout 验证。工具描述增强 0/31 是已记录负结果，不能隐藏。","Rules for a 31-case bucket may memorize local patterns and require frozen-holdout validation. Tool-description enhancement at 0/31 is a recorded negative result and must remain visible.")}</p></article>
<article class="card risk high"><h3>{pair("自动 Agent 边界","Automated-agent boundary")}</h3><p>{pair("Agent 可实现候选、登记证据和运行评测，但不得修改真值、删除难例、降低阈值或把无结果任务标成成功。","An agent may implement candidates, register evidence, and run evaluations, but may not edit truth, remove hard cases, lower thresholds, or mark a result-less task successful.")}</p></article>
</div></section>

<section class="section"><h2>{pair("当前证据成熟度（定性，不是百分比）","Current evidence maturity (qualitative, not percentages)")}</h2>
<div class="card maturity">
<div class="maturity-row"><span>{pair("A/B 架构与 100 条对照","A/B architecture and 100-case comparison")} · <b>{pair("较强","strong")}</b></span><span class="maturity-track"><span class="maturity-fill strong"></span></span></div>
<div class="maturity-row"><span>{pair("B pure-audio 452 组合","B pure-audio 452 combination")} · <b>{pair("局部","scoped")}</b></span><span class="maturity-track"><span class="maturity-fill partial"></span></span></div>
<div class="maturity-row"><span>Hybrid C · <b>{pair("早期","early")}</b></span><span class="maturity-track"><span class="maturity-fill low"></span></span></div>
<div class="maturity-row"><span>{pair("参数 + 最终车态真值","Parameter + final-state truth")} · <b>{pair("早期","early")}</b></span><span class="maturity-track"><span class="maturity-fill low"></span></span></div>
<div class="maturity-row"><span>{pair("真实车内分布","Real in-car distribution")} · <b>{pair("不足","insufficient")}</b></span><span class="maturity-track"><span class="maturity-fill low"></span></span></div>
</div></section>

<section class="section"><h2>{pair("分阶段补齐路线：何时能声称 99%","Phased closure plan: when 99% may be claimed")}</h2><div class="steps">
<article class="step"><h3>{pair("冻结合同与 holdout","Freeze the contract and holdout")}</h3><p>{pair("冻结样本、初始车态、参数、最终态、危险动作/no-op 真值和阈值；开发错误桶与 holdout 隔离。","Freeze samples, initial state, parameters, final state, dangerous-action/no-op truth, and thresholds; isolate development buckets from holdout.")}</p></article>
<article class="step"><h3>{pair("建立多条件分桶","Build multi-condition buckets")}</h3><p>{pair("至少按音色/口音、噪声、AEC 双讲、乘员、VAD/停顿/打断、多轮 KV、危险/闲聊与硬件网络分桶。","At minimum bucket by voice/accent, noise, AEC double-talk, passenger, VAD/pause/interruption, multi-turn KV, dangerous/chat, and hardware/network conditions.")}</p></article>
<article class="step"><h3>{pair("全链路真值与重复试验","End-to-end truth and repeated trials")}</h3><p>{pair("每条检查工具、参数、顺序、回执和最终车态；多 seed 重复，报告每桶与总体置信区间，并加入真实车内回放。","Check tool, parameters, order, receipt, and final state for every case. Repeat across seeds, report bucketed and aggregate confidence intervals, and include real in-car replay.")}</p></article>
<article class="step"><h3>{pair("允许 99% 声明的硬门","Hard gate for a 99% claim")}</h3><p>{pair("只有冻结 holdout 上“参数 + 最终车态”成功率的置信区间下界达到 99%，危险误控为 0，所有预注册关键桶过门，重复 seed 和真实车内回放不退化，才可按该明确范围声称 99%。","Only when the frozen-holdout confidence-interval lower bound for parameter + final-state success reaches 99%, dangerous mis-controls are zero, every preregistered critical bucket passes, and repeated seeds plus real in-car replay do not regress may 99% be claimed for that explicit scope.")}</p></article>
</div></section>
<div class="legend"><a class="btn" href="{BASE}/automation/candidates/">{pair("候选","Candidates")}</a><a class="btn" href="{BASE}/automation/h20/">{pair("评测","Evaluation")}</a><a class="btn" href="{BASE}/automation/selection/">{pair("选择","Selection")}</a><a class="btn" href="{BASE}/automation/case-hybrid-c/">{pair("Hybrid C 案例","Hybrid C case")}</a></div>"""
    return shell("局限与证据审计", "Limitations and evidence audit",
                 "limitations", body, snapshot)


def hybrid_case(snapshot=None):
    snapshot = snapshot or empty_snapshot()
    body = hero("完整案例：Hybrid C", "Full case: Hybrid C",
        "这个案例展示自动化为什么需要“范围、硬门和 partial”：B 有 452 条组合结果，Hybrid C 目前只有 4 条冒烟与 31 条错误桶局部证据，不能混成同一基线。",
        "This case shows why scope, hard gates, and partial exist: B has a 452-case combination result, while Hybrid C currently has only four smoke cases and scoped evidence on a 31-case error bucket. They are not one baseline.",
        '<span class="badge fact">Measured</span><span class="badge pending">No extrapolation from 4 cases</span>')
    body += f"""<section class="section" id="radar"><h2>{pair("1. Radar 建议进入日报","1. Radar advice enters the report")}</h2>
<p>{pair("RelayS2S 提醒安全控制可在生成前后加结构化约束；Voice Memory 提醒把跨轮状态做成显式记忆；Qwen-UI-Agent 提供 typed action / UI grounding 的参考。它们是技术证据，不是 Harness 已有效的结论。","RelayS2S suggested structured safety constraints around generation; Voice Memory suggested explicit cross-turn state; Qwen-UI-Agent informed typed action and UI grounding. These were external evidence, not proof of Harness gains.")}</p></section>
<section class="section" id="report"><h2>{pair("2. 从建议到问题","2. From advice to question")}</h2>
<div class="decision"><article class="card"><b>{pair("现象","Observed problem")}</b><p>{pair("确认回执冗长、复杂动作解析不稳定、真实 ASR 路径有可隐藏时延。","Verbose confirmations, unstable complex-action parsing, and latency opportunities on the real ASR path.")}</p></article><div class="arrow">→</div><article class="card"><b>{pair("实验问题","Experiment question")}</b><p>{pair("能否组合低风险确定性组件，提高完成与工具执行，同时保持 e2e P95？","Can low-risk deterministic components improve completion and tool execution while preserving e2e P95?")}</p></article></div></section>
<section class="section" id="candidate"><h2>{pair("3. 组件逐步形成 Hybrid C","3. Components form Hybrid C")}</h2><div class="timeline">
<article class="event"><b>{pair("紧凑回执","Compact receipt")}</b> — {pair("减少确认文本和 TTS 尾部。","Reduce confirmation text and TTS tail.")}</article>
<article class="event"><b>grouped MoE</b> — {pair("按意图组路由专门解析器。","Route intent groups to specialized resolvers.")}</article>
<article class="event"><b>{pair("确定性确认","Deterministic confirmation")}</b> — {pair("对可确定动作不依赖自由生成。","Avoid free-form generation for deterministic confirmations.")}</article>
<article class="event"><b>Relay {pair("安全前缀","safety prefix")}</b> — {pair("在可执行动作前注入不可绕过的安全上下文。","Inject non-bypassable safety context before executable actions.")}</article>
<article class="event"><b>{pair("真实 ASR 预取","Real-ASR prefetch")}</b> — {pair("只预取、不提前提交，在真实音频路径复用等待时间。","Prefetch without early commit, reusing wait time on the real audio path.")}</article>
<article class="event"><b>typed resolver</b> — {pair("把槽位和动作类型解析成可校验结构。","Parse slots and action types into a validated structure.")}</article>
</div></section>
<section class="section" id="evaluation"><h2>{pair("4. 真实结果，严格分范围","4. Measured results, strictly scoped")}</h2>
<h3>{pair("B pure-audio 组合 · 452 条评测","B pure-audio combination · 452 cases")}</h3><div class="metrics">
<div class="metric"><b>99.56%</b><small>{pair("组合完成率","combined completion")}</small></div>
<div class="metric"><b>81.64%</b><small>{pair("工具执行率","tool execution")}</small></div>
<div class="metric"><b>1241.6ms</b><small>e2e P95</small></div></div>
<p class="callout bad">{pair("这些数字属于 B pure-audio 组合，不属于 Hybrid C。B 的时延通过 1.6s 硬门；99.56% 是组合完成率，不能替代 81.64% 的工具执行准确性，因此准确率门未通过。","These numbers belong to the B pure-audio combination, not Hybrid C. B passes the 1.6s latency gate, but 99.56% combined completion cannot replace 81.64% tool-execution accuracy, so the accuracy gate fails.")}</p>
<h3>{pair("4 条 Hybrid C 冒烟","Four-case Hybrid C smoke")}</h3><div class="metrics">
<div class="metric"><b>4 / 4</b><small>{pair("仅该冒烟集","this smoke set only")}</small></div>
<div class="metric"><b>≈1195ms</b><small>e2e</small></div>
<div class="metric"><b>≈975ms</b><small>call</small></div></div>
<p class="callout">{pair("4 条样本证明链路可工作，不证明总体准确率，也不能外推到 452 或 122 条集合。call 时延也不能冒充 e2e。","Four cases prove the path can work; they do not establish overall accuracy and cannot be extrapolated to 452 or 122 cases. Call latency is not e2e.")}</p>
<h3>{pair("错误桶与淘汰项","Error bucket and rejected item")}</h3><div class="grid">
<article class="card"><h3>0 → 24 / 31</h3><p>{pair("针对 31 条错误桶的组件修复覆盖到 24 条：有显著局部证据，但仍不是完整集通过。","A component fix covered 24 of a 31-case error bucket: meaningful partial evidence, not a full-set pass.")}</p></article>
<article class="card"><h3>0 / 31</h3><p>{pair("“增强工具描述”没有修复任何一条，因此淘汰并保留负结果，避免下一轮重复。","Tool-description enhancement fixed none, so it was rejected and recorded as a negative result.")}</p></article>
</div></section>
<section class="section" id="decision"><h2>{pair("5. 决策树：为什么保留 partial","5. Decision tree: why retain partial")}</h2><div class="steps">
<article class="step"><h3>{pair("证据有效吗？是","Valid evidence? Yes")}</h3><p>{pair("真实 ASR、独立 worker、范围和时延口径可追溯。","Real ASR, isolated workers, scope, and latency definitions are traceable.")}</p></article>
<article class="step"><h3>{pair("整体过硬门吗？尚未建立","Overall gates pass? Not established")}</h3><p>{pair("B 的 452 组合 e2e 1241.6ms 过门、工具执行 81.64% 未达 99%；Hybrid C 尚无同口径 452 全量，因此更不能 qualified / pareto。","B's 452-case combination passes e2e at 1241.6ms but misses 99% with 81.64% tool execution. Hybrid C lacks a like-for-like 452-case run and therefore cannot be qualified or Pareto.")}</p></article>
<article class="step"><h3>{pair("有可拆、可复验的局部收益吗？有","Separable, repeatable partial gain? Yes")}</h3><p>{pair("31 错误桶修到 24/31，且组件边界清楚，因此登记 retained components；0/31 的描述增强不保留。","The 31-case bucket improved to 24/31 with clear component boundaries, so those components are retained. The 0/31 description enhancement is not.")}</p></article>
</div></section>
<section class="section" id="publish"><h2>{pair("6. 正确的发布措辞","6. Correct publishing language")}</h2>
<p class="callout ok">{pair("“B pure-audio 组合在 452 条评测中 e2e P95 1241.6ms 过时延门，但工具执行率 81.64% 未过 99% 准确率门。Hybrid C 目前只有 4/4 smoke 与 31 错误桶 24/31 的局部证据，尚无同口径 452 全量。”","“On 452 cases, the B pure-audio combination passed latency with e2e P95 1241.6ms but missed the 99% accuracy gate with 81.64% tool execution. Hybrid C currently has only a 4/4 smoke and scoped 24/31 error-bucket evidence, with no like-for-like 452-case run.”")}</p>
<div class="legend"><a class="btn" href="{BASE}/automation/research/">{pair("调研","Research")}</a><a class="btn" href="{BASE}/automation/reports/">{pair("日报","Reports")}</a><a class="btn" href="{BASE}/automation/candidates/">{pair("候选","Candidates")}</a><a class="btn" href="{BASE}/automation/h20/">{pair("评测","Evaluation")}</a><a class="btn" href="{BASE}/automation/selection/">{pair("选择","Selection")}</a><a class="btn" href="{BASE}/automation/publishing/">{pair("发布","Publishing")}</a><a class="btn" href="{BASE}/automation/limitations/">{pair("局限审计","Limitations audit")}</a></div></section>"""
    return shell("Hybrid C 完整案例", "Hybrid C full case", "case-hybrid-c", body, snapshot)


PAGES = {
    "index": overview,
    "research": research,
    "reports": reports,
    "candidates": candidates,
    "h20": h20,
    "selection": selection,
    "publishing": publishing,
    "limitations": limitations,
    "case-hybrid-c": hybrid_case,
}


def build(root):
    target = os.path.join(root, "docs", "automation")
    os.makedirs(target, exist_ok=True)
    snapshot = load_snapshot(root)
    expected = set()
    for slug, renderer in PAGES.items():
        folder = target if slug == "index" else os.path.join(target, slug)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "index.html")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(renderer(snapshot))
        expected.add(os.path.normcase(os.path.abspath(path)))
    for current, _, names in os.walk(target):
        for name in names:
            path = os.path.normcase(os.path.abspath(os.path.join(current, name)))
            if name.endswith(".html") and path not in expected:
                os.remove(path)
    return len(PAGES)


if __name__ == "__main__":
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"automation pages built: {build(ROOT)}")
