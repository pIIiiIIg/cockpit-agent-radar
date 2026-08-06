#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the public, bilingual automation-system guide.

The facts and page structure live here; docs/automation is generated output.
The renderer deliberately has no template/runtime dependency.
"""
import html
import os


BASE = "https://piiiiiig.github.io/cockpit-agent-radar"

STAGES = [
    ("research", "论文调研", "Research", "抓取、去重、摘要与全文精读",
     "Fetch, deduplicate, brief, and review full text", "script"),
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
]


def esc(value):
    return html.escape(str(value or ""), quote=True)


def pair(zh, en, tag="span"):
    return (f'<{tag} class="l-zh">{esc(zh)}</{tag}>'
            f'<{tag} class="l-en">{esc(en)}</{tag}>')


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
.verified{color:var(--ok)}.pending{color:var(--warn)}.fact{color:var(--ok)}
.flow{display:grid;grid-template-columns:repeat(6,1fr);gap:24px;margin:24px 0 34px;
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
.decision{grid-template-columns:1fr}.site .sub{display:none}}@media(max-width:480px){
.wrap{padding:12px 12px 48px}.flow{grid-template-columns:1fr}.toolbar{margin-left:0;width:100%}
.hero{padding-top:20px}.navline{grid-template-columns:1fr}.navline a:last-child{text-align:left}}
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
        prev_slug, next_slug = "selection", "publishing"
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


def shell(title_zh, title_en, slug, body):
    return f"""<!doctype html><html lang="zh" data-lang="zh"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title_zh)} · cockpit-agent-radar</title><style>{STYLE}</style></head>
<body><div class="wrap">{header()}<main id="main">{body}</main>{navline(slug)}
<footer>{pair("事实状态截至 2026-08-06；实测与待验证严格分开。","Evidence status as of 2026-08-06; measured and pending claims are separated.")}</footer>
</div><script>{JS}</script></body></html>"""


def hero(zh, en, intro_zh, intro_en, badges=""):
    return (f'<section class="hero"><h1>{pair(zh,en)}</h1><p>{pair(intro_zh,intro_en)}</p>'
            f'<div class="legend">{badges}</div></section>')


def stage_links():
    rows = []
    for i, (slug, zh, en, dzh, den, owner) in enumerate(STAGES, 1):
        rows.append(f"""<a class="flow-node" href="{BASE}/automation/{slug}/">
<span class="num">{i}</span><h2>{pair(zh,en)}</h2><p>{pair(dzh,den)}</p>
<span class="badge {owner}">{pair("Cursor 参与" if owner=="cursor" else "纯脚本",
"Cursor-assisted" if owner=="cursor" else "Scripted")}</span></a>""")
    return "".join(rows)


def overview():
    badges = (f'<span class="badge cursor">{pair("紫：Cursor 模型参与","Violet: Cursor-assisted")}</span>'
              f'<span class="badge script">{pair("蓝：确定性脚本","Blue: deterministic scripts")}</span>'
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
<p class="callout ok"><b>{pair("完整案例：","Full case:")}</b> <a href="{BASE}/automation/case-hybrid-c/">{pair("Hybrid C 为什么准确率没过硬门仍保留 partial →","Why Hybrid C was retained as partial despite missing the accuracy gate →")}</a></p>"""
    return shell("自动化系统总览", "Automation overview", "research", body).replace(
        navline("research"), "")


def research():
    body = hero("论文调研", "Research",
        "调研层先用确定性脚本扩大召回，再让 Cursor 只处理值得全文精读的证据；“摘要速读”和“正文精读”在页面上明确分级。",
        "Deterministic scripts maximize recall; Cursor spends time only on evidence worth full-text review. Abstract briefs and full-text reviews remain visibly distinct.",
        '<span class="badge script">Fetch/score: script</span><span class="badge cursor">Full text: Cursor</span><span class="badge verified">3 runs/day verified</span>')
    body += f"""<section class="section"><h2>{pair("从四源到站内证据","From four sources to site evidence")}</h2><div class="steps">
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
    return shell("论文调研", "Research", "research", body)


def reports():
    body = hero("问题驱动日报", "Problem-driven reports",
        "日报不是“今天有哪些论文”，而是把 Harness 的最新失败、指标和假设，与核验过的外部证据对齐。",
        "The report is not a paper digest. It aligns current Harness failures, metrics, and hypotheses with verified external evidence.",
        '<span class="badge cursor">Cursor synthesis</span><span class="badge script">Scripted publish</span>')
    body += f"""<section class="section"><h2>{pair("输入、推理、输出","Input, reasoning, output")}</h2><div class="grid">
<article class="card"><h3>{pair("项目快照","Project snapshot")}</h3><ul><li>StreamingModelHarness {pair("最新提交与组件","latest commit and components")}</li><li>{pair("组合准确率、工具执行、端到端 P95","combined accuracy, tool execution, e2e P95")}</li><li>{pair("错误桶、负结果、待验证假设","error buckets, negative results, hypotheses")}</li></ul></article>
<article class="card"><h3>{pair("证据映射","Evidence mapping")}</h3><p>{pair("每个方向写清：当前项目问题→项目证据→相关技术→最小实验→成功门槛。论文数字只能标成论文结果，不能冒充项目实测。","Each direction states project problem→project evidence→related technique→minimum experiment→success gate. Paper numbers remain paper results, never project measurements.")}</p></article>
<article class="card"><h3>{pair("两份日报","Two reports")}</h3><p>{pair("详细增量调研包含 P0/P1/P2、统一技术卡和风险；精简日报每行压缩成“方向（问题；解法；实验）”。","The deep report contains P0/P1/P2, normalized technology cards, and risks. The brief compresses each item to direction (problem; mechanism; experiment).")}</p></article>
</div></section>
<div class="callout"><b>{pair("发布边界：","Publishing boundary:")}</b> {pair("Cursor 任务只改 reports/、project_status/ 和构建后的 docs/；不修改 Harness，不调用 Kimi/Moonshot。测试和构建通过后才由发布脚本提交。","The Cursor task may edit only reports/, project_status/, and generated docs/. It does not modify Harness or call Kimi/Moonshot. Publishing commits only after tests and build pass.")}</div>
<section class="section"><h2>{pair("一次建议如何变成可测问题","How advice becomes a testable question")}</h2>
<div class="decision"><article class="card"><b>{pair("证据","Evidence")}</b><p>Voice Memory / RelayS2S / Qwen-UI-Agent</p></article><div class="arrow">→</div><article class="card"><b>{pair("问题","Question")}</b><p>{pair("能否在不破坏真值和时延的前提下修复确认与 typed action？","Can confirmation and typed actions improve without harming truth or latency?")}</p></article></div>
</section><p><a href="{BASE}/automation/case-hybrid-c/#report">{pair("案例关联：日报建议到 Hybrid C →","Case link: report advice to Hybrid C →")}</a></p>"""
    return shell("问题驱动日报", "Reports", "reports", body)


def candidates():
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
<p><a href="{BASE}/automation/case-hybrid-c/#candidate">{pair("案例关联：Hybrid C 的六个组件怎样逐步进入 →","Case link: how six Hybrid C components entered →")}</a></p>"""
    return shell("实验候选", "Candidates", "candidates", body)


def h20():
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
<p><a href="{BASE}/automation/case-hybrid-c/#evaluation">{pair("案例关联：Hybrid C 的 452 条与 4 条 smoke 数据 →","Case link: Hybrid C's 452-case and 4-case smoke results →")}</a></p>"""
    return shell("H20 隔离评测", "H20 evaluation", "h20", body)


def selection():
    body = hero("选择、Pareto 与局部留存", "Selection, Pareto, and partial retention",
        "选择器不只输出“赢/输”。它先执行不可协商的硬门，再区分 qualified、pareto、partial、rejected 与 invalid。",
        "Selection is not merely win/lose. Non-negotiable gates run first, followed by qualified, pareto, partial, rejected, or invalid.",
        '<span class="badge script">Hard gates: script</span><span class="badge fact">Accuracy ≥99%</span><span class="badge fact">e2e P95 ≤1.6s</span>')
    body += f"""<section class="section"><h2>{pair("五种结果","Five outcomes")}</h2><div class="grid">
<article class="card"><h3 class="verified">qualified</h3><p>{pair("所有硬门通过，且证据范围完整，可作为合格候选继续。","All hard gates pass with complete evidence.")}</p></article>
<article class="card"><h3 class="verified">pareto</h3><p>{pair("在准确率、时延或能力覆盖上不可被另一合格候选全面支配。","Not dominated by another qualified candidate across accuracy, latency, and coverage.")}</p></article>
<article class="card"><h3 class="pending">partial</h3><p>{pair("整体未过门，但某个可拆组件在严格范围内有真实收益，登记 retained components，禁止宣传为整体成功。","Overall gates fail, but a separable component has scoped evidence. Register it as retained; never call the whole candidate successful.")}</p></article>
<article class="card"><h3 class="bad">rejected</h3><p>{pair("证据有效但无收益、退化或被更简单方案支配；负结果进入 registry，避免重复试验。","Valid evidence shows no gain, regression, or domination; record the negative result.")}</p></article>
<article class="card"><h3 class="bad">invalid</h3><p>{pair("服务失败、数据污染、评测路径不真实、样本不足或真值被修改，不能据此比较。","Service failure, contamination, unreal path, insufficient scope, or modified truth makes comparison invalid.")}</p></article>
</div></section>
<section class="section"><h2>{pair("决策顺序","Decision order")}</h2><div class="steps">
<article class="step"><h3>{pair("先查有效性","Validate evidence")}</h3><p>{pair("路径、样本、日志和资源隔离不完整，直接 invalid。","Incomplete path, sample, logs, or isolation means invalid.")}</p></article>
<article class="step"><h3>{pair("再过硬门","Apply hard gates")}</h3><p>{pair("组合准确率至少 99%，e2e P95 不高于 1.6s；不能互相抵偿。","Combined accuracy must be at least 99%; e2e P95 at most 1.6s. One cannot compensate for the other.")}</p></article>
<article class="step"><h3>{pair("最后看 Pareto 与局部证据","Then Pareto and partial evidence")}</h3><p>{pair("过门候选比较前沿；未过门候选只允许拆出有独立测试、清晰边界的 retained component。","Gate passers compete on the frontier. Gate failures may retain only independently tested, clearly scoped components.")}</p></article>
</div></section>
<p><a href="{BASE}/automation/case-hybrid-c/#decision">{pair("案例关联：为什么 Hybrid C 是 partial 而非 qualified →","Case link: why Hybrid C is partial, not qualified →")}</a></p>"""
    return shell("选择与留存", "Selection", "selection", body)


def publishing():
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
    return shell("发布与反馈", "Publishing", "publishing", body)


def hybrid_case():
    body = hero("完整案例：Hybrid C", "Full case: Hybrid C",
        "这个案例展示自动化为什么需要“范围、硬门和 partial”：大样本准确率没有过门，但若干组件在独立小范围证据下值得保留。",
        "This case shows why scope, hard gates, and partial exist: large-scope accuracy missed the gate, while several components had independently scoped evidence worth retaining.",
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
<h3>{pair("452 条组合评测","452-case combination evaluation")}</h3><div class="metrics">
<div class="metric"><b>99.56%</b><small>{pair("组合完成率","combined completion")}</small></div>
<div class="metric"><b>81.64%</b><small>{pair("工具执行率","tool execution")}</small></div>
<div class="metric"><b>1241.6ms</b><small>e2e P95</small></div></div>
<p class="callout bad">{pair("时延通过 1.6s 硬门；准确率门按要求未通过。99.56% 是“组合完成率”，不能替代工具执行准确性；81.64% 明显低于 99%。","Latency passes the 1.6s gate; the required accuracy gate does not. 99.56% is combined completion and cannot replace tool-execution accuracy; 81.64% is below 99%.")}</p>
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
<article class="step"><h3>{pair("整体过硬门吗？否","Overall gates pass? No")}</h3><p>{pair("e2e 1241.6ms 过门；工具执行 81.64% 未达到 99%，因此不能 qualified / pareto。","e2e 1241.6ms passes; tool execution 81.64% misses 99%, so it cannot be qualified or Pareto.")}</p></article>
<article class="step"><h3>{pair("有可拆、可复验的局部收益吗？有","Separable, repeatable partial gain? Yes")}</h3><p>{pair("31 错误桶修到 24/31，且组件边界清楚，因此登记 retained components；0/31 的描述增强不保留。","The 31-case bucket improved to 24/31 with clear component boundaries, so those components are retained. The 0/31 description enhancement is not.")}</p></article>
</div></section>
<section class="section" id="publish"><h2>{pair("6. 正确的发布措辞","6. Correct publishing language")}</h2>
<p class="callout ok">{pair("“Hybrid C 在 452 条评测中 e2e P95 1241.6ms 过时延门，但工具执行率 81.64% 未过 99% 准确率门；若干组件因 31 错误桶达到 24/31 而局部留存。4/4 smoke 仅证明小范围链路。”","“On 452 cases, Hybrid C passed latency with e2e P95 1241.6ms but missed the 99% accuracy gate with 81.64% tool execution. Some components were retained after improving a 31-case bucket to 24/31. The 4/4 smoke proves only that small path.”")}</p>
<div class="legend"><a class="btn" href="{BASE}/automation/research/">{pair("调研","Research")}</a><a class="btn" href="{BASE}/automation/reports/">{pair("日报","Reports")}</a><a class="btn" href="{BASE}/automation/candidates/">{pair("候选","Candidates")}</a><a class="btn" href="{BASE}/automation/h20/">{pair("评测","Evaluation")}</a><a class="btn" href="{BASE}/automation/selection/">{pair("选择","Selection")}</a><a class="btn" href="{BASE}/automation/publishing/">{pair("发布","Publishing")}</a></div></section>"""
    return shell("Hybrid C 完整案例", "Hybrid C full case", "case-hybrid-c", body)


PAGES = {
    "index": overview,
    "research": research,
    "reports": reports,
    "candidates": candidates,
    "h20": h20,
    "selection": selection,
    "publishing": publishing,
    "case-hybrid-c": hybrid_case,
}


def build(root):
    target = os.path.join(root, "docs", "automation")
    os.makedirs(target, exist_ok=True)
    expected = set()
    for slug, renderer in PAGES.items():
        folder = target if slug == "index" else os.path.join(target, slug)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "index.html")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(renderer())
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
