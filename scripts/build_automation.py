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
    solution_payload = safe_json(
        os.path.join(data_dir, "harness_solutions.json"), {})
    solution_rows = (
        solution_payload.get("components", [])
        if isinstance(solution_payload, dict) else [])
    solution_rows = [row for row in solution_rows if isinstance(row, dict)]
    ledger_payload = safe_json(
        os.path.join(data_dir, "handoff", "ledger.json"), {})
    activity_payload = safe_json(
        os.path.join(data_dir, "experiment_activity.json"), {})
    cost_status = safe_json(os.path.join(data_dir, "cost_status.json"), {})
    ledger_days = []
    if isinstance(ledger_payload, dict):
        for day, value in sorted(
                ledger_payload.get("days", {}).items(), reverse=True):
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(day)):
                continue
            stages = value.get("stages", {}) if isinstance(value, dict) else {}
            ledger_days.append({
                "date": day,
                "stages": {
                    stage: str(stages.get(stage, {}).get("status", "missing"))
                    for stage in (
                        "fulltext_review", "problem_report", "duplex_report",
                        "candidate_publish", "candidate_ack", "offline_replay",
                        "h20_evaluation", "result_manifest", "radar_writeback")
                },
            })
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
        "solution_count": sum(
            row.get("recommended") is True for row in solution_rows),
        "solution_status": (
            solution_payload.get("source", {}).get("status", "stale")
            if isinstance(solution_payload.get("source"), dict) else "stale"),
        "ledger_days": ledger_days,
        "experiment_days": (
            activity_payload.get("days", {})
            if isinstance(activity_payload, dict)
            and isinstance(activity_payload.get("days"), dict) else {}),
        "cost_status": cost_status if isinstance(cost_status, dict) else {},
        "build_date": build_time.date().isoformat(),
        "build_time": build_time.isoformat(timespec="minutes"),
    }


def empty_snapshot():
    return load_snapshot(os.path.join(os.path.dirname(__file__), "__missing__"))


def detail_block(reason_zh, reason_en, run_zh, run_en, boundary_zh, boundary_en):
    return (
        '<details class="item-detail"><summary tabindex="0">'
        + pair("展开详细解释", "Expand detailed explanation") + "</summary>"
        + f'<h4>{pair("为什么需要","Why it exists")}</h4><p>{pair(reason_zh,reason_en)}</p>'
        + f'<h4>{pair("如何运行与留下什么","How it runs and what it leaves")}</h4>'
        + f'<p>{pair(run_zh,run_en)}</p>'
        + f'<h4>{pair("失败方式与当前边界","Failure modes and current boundary")}</h4>'
        + f'<p>{pair(boundary_zh,boundary_en)}</p></details>')


DETAILS = {
    "research": [
        ("arXiv / GitHub", "统一适配器防止不同来源字段和时间口径污染排序。",
         "Normalized adapters keep source-specific fields and clocks from corrupting ranking.",
         "每个适配器只读官方公开元数据，输出统一 title、URL、时间、来源和标签，随后才进入评分。",
         "Each adapter reads public official metadata and emits normalized title, URL, time, source, and tags before scoring.",
         "源超时只影响该源；陌生仓库不执行。缺字段会降级或丢弃并留下抓取日志。",
         "A source timeout is isolated; unknown repositories are never executed. Missing fields degrade or reject the row with fetch logs."),
        ("关键词评分", "先去重再限流，避免旧镜像占掉新条目配额。",
         "Deduplication precedes caps so old mirrors cannot consume the new-item budget.",
         "URL、canonical_id 和 mirror_of 联合识别同题；标题关键词分层加权，更新旧条目后再截新条目。",
         "URL, canonical_id, and mirror_of identify mirrors; tiered title keywords score relevance, existing rows update before new rows are capped.",
         "评分只代表雷达相关性，不代表论文质量；镜像关系不确定时不强行合并。",
         "The score is radar relevance, not paper quality; uncertain mirrors are not forcibly merged."),
        ("零模型摘要回填", "没有 Cursor 班次时也要让新论文有可读但不冒充精读的入口。",
         "New papers need a readable entry even when no Cursor review shift runs, without impersonating full-text review.",
         "脚本从公开摘要生成 abstract_backfill，写 explanations.json 并在页面明确显示“摘要速读”。",
         "A script derives abstract_backfill from the public abstract, stores it in explanations.json, and labels it Abstract brief.",
         "它不读正文、不进入 review_history，也不能支撑方法细节或工程结论。",
         "It does not read full text, enter review_history, or support method-detail and engineering claims."),
        ("Cursor 全文精读", "只有正文、项目页和官方代码能支持方法、结果、局限与开放状态的核验。",
         "Only full text, project pages, and official code can substantiate method, result, limitation, and openness claims.",
         "Cursor 逐项写 tl_dr、方法、流程、结果、局限、开放状态和项目适配判断，并保留论文数字与项目数字的边界。",
         "Cursor writes the summary, method, workflow, findings, limits, openness, and project-fit judgment while separating paper and project numbers.",
         "无法获取正文时不得标 fulltext；编辑判断必须标注为判断，不能伪装成论文原结论。",
         "Unavailable full text cannot be marked fulltext; editorial inference must remain labeled and never masquerade as a paper conclusion."),
        ("review_history.json", "状态迁移历史用于回答“具体哪天真正精读了哪些论文”。",
         "Transition history answers exactly which papers were truly reviewed on which day.",
         "只有 abstract/missing 到 editorial+fulltext 的有效迁移写入，记录北京时间、论文源、站内详情、run 和镜像关系。",
         "Only valid transitions into editorial+fulltext are recorded with Beijing time, source, detail page, run, and mirror relation.",
         "重复 ID 幂等；历史回填必须标 backfilled，不能猜测旧批次时间。",
         "Duplicate IDs are idempotent; historical recovery is marked backfilled and never invents old run times."),
        ("定时", "抓取与精读解耦，避免模型不可用拖住公开站点。",
         "Fetch and full-text review are decoupled so model unavailability cannot stall the public site.",
         "云端三班抓取并建站，本地班次按新论文和历史缺口精读；两者通过数据文件和完成哨兵交接。",
         "Three cloud shifts fetch and build; local shifts review new papers and backlog, handing off through data files and completion sentinels.",
         "时间表是目标调度，不代表每班都有新条目；无结果必须如实记录。",
         "The schedule is a target cadence, not proof each shift has new items; no-result runs remain explicit."),
        ("重试与锁", "多个本地班次同时改 explanations 和 reports 会产生丢更新。",
         "Concurrent local shifts editing explanations and reports would lose updates.",
         "原子 PID 锁串行化发布，Cursor 最多重试三次；测试、构建和 push 共享同一批次状态。",
         "An atomic PID lock serializes publishing, Cursor retries up to three times, and tests/build/push share one batch state.",
         "锁超时或进程归属不明时停止，不用模糊杀进程恢复。",
         "Lock timeout or uncertain process ownership stops the run; broad process killing is not a recovery mechanism."),
        ("停止条件", "自动化最危险的失败是跳过步骤却仍返回成功。",
         "The most dangerous automation failure is skipping work while returning success.",
         "完成哨兵、源文件 diff、测试、构建、远端 rebase 和 Pages smoke 逐层校验。",
         "Completion sentinel, source diff, tests, build, remote rebase, and Pages smoke validate successive layers.",
         "任何源冲突、哨兵缺失或重试耗尽都非零退出；生成 docs 冲突才允许重建。",
         "Source conflicts, missing sentinels, or exhausted retries exit nonzero; only generated-doc conflicts may be rebuilt."),
    ],
    "reports": [
        ("最新详细", "详细增量调研保存完整证据链，供候选设计和之后复核。",
         "The detailed incremental report preserves the evidence chain for candidate design and later review.",
         "它按项目问题组织 P0/P1/P2、论文来源、论文结果、工程实验和成功门槛。",
         "It organizes P0/P1/P2 by project problem, paper sources, paper findings, engineering experiments, and success gates.",
         "报告日期不是实验日期；没有新项目实测时必须明确沿用旧快照。",
         "Report date is not experiment date; absent new project measurements, the prior snapshot must be stated."),
        ("最新每日", "精简日报让执行者快速看到今天要验证什么，而不是重读长报告。",
         "The daily brief lets operators see what to validate without rereading the long report.",
         "每行压缩为方向、问题、机制、最小实验和门槛，并链接对应详细报告。",
         "Each line compresses direction, problem, mechanism, minimum experiment, and gate, linking the detailed report.",
         "压缩不能删除证据范围和待验证标记，也不能把论文结果写成项目收益。",
         "Compression cannot remove scope or pending labels, nor turn paper results into project gains."),
        ("报告总天数", "报告天数用于观察连续性，不是研究质量或论文数量指标。",
         "Report-day count measures continuity, not research quality or paper volume.",
         "构建器从 reports 文件名解析日期，并分别计入详细调研与每日简报。",
         "The builder parses dates from report filenames and tracks detailed and daily forms separately.",
         "缺一种报告时页面仍构建并显示现有产物，不伪造配对。",
         "If one report form is missing, the page builds with existing artifacts and never invents a pair."),
        ("项目快照", "日报必须从项目真实失败和指标出发，否则只会变成资讯摘抄。",
         "Reports must start from real project failures and metrics or collapse into news clipping.",
         "快照读取提交、架构、基准、错误桶和负结果；报告引用时保留时间与口径。",
         "The snapshot supplies commits, architecture, benchmarks, error buckets, and negatives with timestamps and definitions.",
         "快照陈旧时只能提出实验，不能声称当前代码已有收益。",
         "A stale snapshot can motivate an experiment but cannot prove a current-code gain."),
        ("证据映射", "论文概念必须落到一个可证伪项目问题，而不是按热度选题。",
         "A paper concept must map to a falsifiable project problem rather than trend-driven selection.",
         "每个方向保留项目问题→项目证据→外部技术→最小实验→成功门槛，并写 source_paths。",
         "Each direction records project problem→project evidence→external technique→minimum experiment→success gate plus source_paths.",
         "工程组合属于编辑判断；论文没有测试 Harness 时必须明确说未证明。",
         "Engineering composition is editorial judgment; papers that did not test the Harness prove nothing about it."),
        ("两份日报", "长短两份产物服务不同读者，但必须共享事实源。",
         "Long and short reports serve different readers but must share one fact source.",
         "详细版保存论证、风险和开放状态；精简版引用同日详细版并保留实验门。",
         "The detailed form keeps reasoning, risks, and openness; the brief points to it and retains experiment gates.",
         "两份数字不一致时构建测试应失败或人工修正，不能各自演化。",
         "If numbers diverge, tests or review must stop publication rather than let two truths evolve."),
        ("Voice Memory / RelayS2S", "外部证据只能启发问题，不能直接成为 Harness 结论。",
         "External evidence may motivate a question but cannot become a Harness conclusion.",
         "报告把论文机制映射到 ASR 纠错、安全前缀或 typed action，并给隔离实验。",
         "The report maps mechanisms to ASR correction, safe prefixing, or typed action and proposes an isolated test.",
         "跨论文组合增加归因风险，必须在候选页拆变量。",
         "Combining papers increases attribution risk and must be decomposed on the Candidates page."),
        ("实验问题", "问题必须同时包含收益目标和不可退化条件。",
         "A question needs both a gain target and non-regression constraints.",
         "输入是项目基线和证据；输出是一个候选合同、样本范围、对照和硬门。",
         "Inputs are project baseline and evidence; output is a candidate contract, sample scope, control, and hard gates.",
         "只写“尝试优化”不可判定成功，不能进入自动执行。",
         "“Try to optimize” is not falsifiable and cannot enter automatic execution."),
    ],
    "candidates": [
        ("先写假设", "日报建议常同时包含多个机制；不拆开就无法知道收益来自哪里。",
         "Report advice often mixes mechanisms; without decomposition, gains cannot be attributed.",
         "把建议改写成“若只改变 X，则 Y 在同一基线/样本上改善且 Z 不退化”。正例是只开紧凑回执比较 token 与 e2e；反例是同时换 MoE、回执、前缀和 resolver。",
         "Rewrite advice as “if only X changes, Y improves on the same baseline/samples while Z does not regress.” A positive example toggles compact receipts alone; a counterexample changes MoE, receipt, prefix, and resolver together.",
         "无法单变量的组合先拆组件微基准与消融；拆不开只能登记 combined evidence，不能归因。",
         "An inseparable combination first needs component microbenchmarks and ablations; otherwise it remains combined evidence with no component attribution."),
        ("独立 worktree", "共享工作树会让并发候选互相覆盖依赖、端口、结果和未提交文件。",
         "A shared tree lets concurrent candidates overwrite dependencies, ports, results, and uncommitted files.",
         "每个 candidate_id 对应 experiment 分支、独立目录、依赖环境、端口段和 run 目录；失败后按记录 PID 清理并删除 worktree，分支保留可复现提交。",
         "Each candidate_id gets an experiment branch, isolated directory, environment, port block, and run directory. Failure cleans recorded PIDs and removes the worktree while retaining reproducible commits.",
         "恢复只读取状态文件和哈希，不复用未知进程；并发受 GPU/显存队列约束，不靠共享缓存冒充独立。",
         "Recovery reads state and hashes, never unknown processes. Concurrency is GPU/memory queued and cannot use shared cache to fake isolation."),
        ("保护真值与门槛", "Agent 同时能改代码和测试时，最容易通过修改考卷制造假提升。",
         "When an agent can edit code and tests, changing the exam is the easiest fake improvement.",
         "protected paths、diff allowlist 和 manifest audit 禁止改真值、删难例、读 manifest 原文、注入 truth text、降低 99%/1600ms 或把基础设施错误移出分母。",
         "Protected paths, diff allowlists, and manifest audit forbid truth edits, case deletion, manifest-transcript shortcuts, truth-text injection, lower 99%/1600ms gates, or removing infrastructure failures from denominators.",
         "任何违规都标 invalid、停止 full/complex 和 push；修复代码后必须从干净基线重跑，不能沿用污染结果。",
         "Any violation marks invalid and blocks full/complex and push. After fixing code, rerun from a clean baseline; contaminated results cannot carry over."),
        ("登记可组合组件", "整套方案失败不等于每个零部件无价值，但组合指标也不能平均分给组件。",
         "A failed whole candidate does not make every component worthless, but shared metrics cannot be divided among components.",
         "experiment registry 记录 parent/baseline、commit、profile、样本/分桶、指标、delta、状态、来源、产物哈希和局限；retained_components 另记 runtime switch、归因、兼容性与下一门。",
         "The experiment registry records parent/baseline, commit, profile, samples/buckets, metrics, delta, status, sources, artifact hashes, and limits; retained_components adds runtime switch, attribution, compatibility, and next gate.",
         "只有 direct/component-specific 证据可 retained；组合或未全量证据为 conditional；0/31 无收益保持 rejected。组合前还要做兼容性和反事实消融。",
         "Only direct/component-specific evidence may be retained; combined or incomplete evidence is conditional; 0/31 no-gain remains rejected. Composition still requires compatibility and counterfactual ablation."),
    ],
    "h20": [
        ("Worker A", "基线与候选不能共享模型进程，否则 KV、配置和显存状态会交叉污染。",
         "Baseline and candidate cannot share a model process because KV, configuration, and GPU state would cross-contaminate.",
         "Worker A 固定 GPU/端口段、PID 清单、日志和 worktree，并把启动配置写入 run metadata。",
         "Worker A pins GPUs/ports, PID inventory, logs, and worktree, writing startup configuration into run metadata.",
         "端口已占用、显存不足或 PID 归属不符时排队或失败，不接管未知服务。",
         "Occupied ports, low memory, or PID ownership mismatch queue or fail; unknown services are never adopted."),
        ("Worker B", "第二 worker 提供同一时间窗内的独立复验或候选对照。",
         "The second worker provides independent confirmation or candidate comparison in the same time window.",
         "它使用另一 GPU/端口/目录集合，结果按 candidate_id 和 artifact hash 回收。",
         "It uses a separate GPU/port/directory set and returns results keyed by candidate_id and artifact hash.",
         "并行只节省墙钟时间，不增加样本数、独立 seed 或统计有效性。",
         "Parallelism saves wall time; it does not add samples, independent seeds, or statistical validity."),
        ("Smoke", "先用小样本发现启动、协议、授权和真实 call 证据问题，避免昂贵全量浪费。",
         "A small set catches startup, protocol, authorization, and real-call evidence failures before an expensive full run.",
         "smoke 读取真实 WAV、发送 100ms 音频块、记录 search/call/首音频和回执，再执行回归门。",
         "Smoke reads real WAV, streams 100ms chunks, records search/call/first audio/receipts, then applies regression gates.",
         "通过只说明链路可工作；4/4 不能估计 99%，也不能绕过 full 与 complex。",
         "Passing only shows the path can work; 4/4 cannot estimate 99% or bypass full and complex."),
        ("452", "全量层提供固定样本上的组合回归，但当前音频和真值仍有审计缺口。",
         "The full layer provides combination regression on a fixed manifest, while current audio and truth still have audit gaps.",
         "runner 遍历 452 manifest 行，解析或生成音频，记录全部入场样本、错误和分母。",
         "The runner traverses 452 manifest rows, resolves or synthesizes audio, and records every admitted sample, error, and denominator.",
         "现有 452 是单音色 clean single-turn，且无参数/最终态真值，不能叫端到端任务成功。",
         "The current 452 set is single-voice clean single-turn with no argument/final-state truth, so it is not end-to-end task success."),
        ("122", "复杂集补多意图、指代、改口和多轮结构，防止简单单轮分数掩盖规划失败。",
         "The complex suite adds multi-intent, reference, correction, and multi-turn structure so simple scores cannot hide planning failures.",
         "每例含 expected_calls、forbidden_calls 与 expected_final_state，分别评分严格序列和状态等价。",
         "Each case carries expected_calls, forbidden_calls, and expected_final_state, scoring strict sequence and state equivalence separately.",
         "当前最终态由调用重放模拟，不是真实车辆回读；合成 122 也不能代替真实分布。",
         "Current final state is simulated by replaying calls, not real vehicle readback; synthetic 122 cannot replace the real distribution."),
        ("pure audio +", "真实音频门阻止 manifest 原文或标签捷径冒充语音理解。",
         "The real-audio gate prevents manifest transcripts or labels from impersonating speech understanding.",
         "B pure 不发送 SoulX；audio-derived 变体必须从 WAV 得到 ASR 文本并记录 provenance。",
         "B pure sends no SoulX; an audio-derived variant must derive ASR from WAV and record provenance.",
         "当前 asr_prefetch 是先完整转写再播放，只有耗时隐藏近似，不是真流式 ASR 并发。",
         "Current asr_prefetch fully transcribes before playback, approximating hidden cost rather than true streaming-ASR concurrency."),
        ("e2e P95", "用户感知首响、真实工具调用和车态落地是不同事件。",
         "Perceived first response, real tool call, and vehicle-state landing are different events.",
         "分别记录 commit→Relay 首音频、commit→call、VAD 元数据与执行回执，不互相替代。",
         "Record commit→Relay first audio, commit→call, VAD metadata, and execution receipt separately.",
         "1241.6ms 只证明 Relay 首响；call P95 1818.7ms，且 runner 没真实等待 0.7s VAD。",
         "1241.6ms proves only Relay first audio; call P95 is 1818.7ms, and the runner does not actually wait the 0.7s VAD."),
        ("安全清理", "GPU 服务失败后遗留进程会污染下一候选。",
         "Processes left by failed GPU services contaminate the next candidate.",
         "启动时登记 PID、端口、命令和目录；finally 仅终止归属匹配的记录进程。",
         "Startup records PID, port, command, and directory; finally terminates only matching recorded processes.",
         "模糊匹配、全局 kill 或删除共享目录被禁止；清理失败使 run 非零。",
         "Broad matching, global kill, and shared-directory deletion are forbidden; cleanup failure makes the run nonzero."),
    ],
    "publishing": [
        ("实验分支", "未过门代码必须可复现但不能污染 main。",
         "Gate-failing code must remain reproducible without contaminating main.",
         "每个 candidate_id 生成安全 experiment 分支，提交源码、README、复现命令和范围结论。",
         "Each candidate_id gets a safe experiment branch with source, README, reproduction command, and scoped conclusion.",
         "分支存在不代表合并或生产；invalid 默认不发布，rejected 仅显式允许才推。",
         "Branch existence is not merge or production approval; invalid is not published, rejected only when explicitly allowed."),
        ("registry + retained", "实验结果与组件证据需要不同粒度的登记。",
         "Experiment outcomes and component evidence require different registry granularity.",
         "experiment registry 保存整套 run 与哈希；retained registry 保存组件开关、归因、兼容性和下一门。",
         "The experiment registry stores whole-run records and hashes; retained registry stores switches, attribution, compatibility, and next gates.",
         "组合指标不能拆给组件，conditional 不得进入默认推荐，负结果不可删除。",
         "Combination metrics cannot be split among components, conditional cannot enter defaults, and negatives cannot be erased."),
        ("网站与 Pages", "本地生成成功不等于用户能访问。",
         "A successful local build does not mean users can access it.",
         "测试互链、转义、无外部运行资源和关键事实后构建 docs、push main，再有限重试 HTTP。",
         "Tests verify links, escaping, no external runtime resources, and facts before docs build, main push, and bounded HTTP retries.",
         "缓存或部署延迟只允许有限重试；页面内容不匹配即发布未完成。",
         "Cache/deploy delay gets bounded retries only; content mismatch means publication is incomplete."),
        ("本地同步与反馈", "定时抓取可能在发布期间推进 main。",
         "Scheduled fetches may advance main during publishing.",
         "发布前后 fetch/rebase；docs 冲突重建，源数据冲突停止。registry 结果进入下一项目快照。",
         "Fetch/rebase before and after work; rebuild docs conflicts, stop on source conflicts. Registry outcomes feed the next snapshot.",
         "禁止 force push；重试耗尽或源冲突需人工接手。",
         "Force push is forbidden; exhausted retries or source conflicts require human takeover."),
    ],
    "selection": [
        ("research_eligible", "研究资格先证明口径可比、真实执行、安全和分桶，不代表可部署。",
         "Research eligibility first proves comparability, real execution, safety, and buckets; it is not deployment readiness.",
         "评分器汇总全部样本和分桶，检查 profile/full/smoke/452/99%/1600ms/complex/baseline。",
         "The scorer aggregates all samples and buckets, checking profile/full/smoke/452/99%/1600ms/complex/baseline.",
         "当前自动化 asr_prefetch=true 运行 audio-derived C，不能替代 strict B pure 基线。",
         "Current automation runs audio-derived C with asr_prefetch=true and cannot replace the strict B pure baseline."),
        ("production_eligible", "生产资格要证明动作语义和最终状态，而不只工具名。",
         "Production eligibility proves action semantics and final state, not only tool name.",
         "在 research 全部门之上要求 expected_args/final_state 覆盖100%与 task success≥99%。",
         "Above all research gates it requires 100% expected_args/final_state coverage and task success ≥99%.",
         "452 manifest 缺这些真值，CarSim 也未真实回读，因此当前历史结果无法取得 production 资格。",
         "The 452 manifest lacks this truth and CarSim is not real readback, so historical results cannot be production-eligible."),
        ("B pure-audio · 452", "该卡用于展示合法但不充分的历史组合证据。",
         "This card shows valid but insufficient historical combination evidence.",
         "分母保留 452 条：369 条 expected-tool 收到成功或无需执行回执，Wilson CI 77.81–84.93%。",
         "The denominator remains 452: 369 expected tools received successful or idempotent receipts, Wilson CI 77.81–84.93%.",
         "49 条仅无需执行，物理执行须分开；标签敏感性上限也远低于99%。",
         "Forty-nine are idempotent-only and physical execution must be separate; label-sensitivity ceilings remain far below 99%."),
        ("Hybrid C · 4-case", "冒烟只保护链路，不估计总体成功率。",
         "Smoke protects path integrity; it does not estimate population success.",
         "四条记录音频、ASR provenance、call 与首音频，用于决定是否值得全量。",
         "Four cases record audio, ASR provenance, call, and first audio to decide whether a full run is warranted.",
         "先完整 ASR 再播放不是真流式并发；不同 452 范围不能计算 delta。",
         "Full ASR before playback is not true streaming concurrency; no delta is valid against a different 452 scope."),
        ("工具描述增强", "负结果可阻止自动化反复尝试同一无效方向。",
         "A negative result stops automation from repeatedly trying the same ineffective direction.",
         "31 条真实混淆桶在同口径比较，0 条修复后登记 rejected 与产物哈希。",
         "Thirty-one confusion cases are compared like-for-like; zero fixes produce a rejected record and artifact hash.",
         "错误桶本身可能过拟合，rejected 结论只覆盖该干预和范围。",
         "The bucket itself may overfit; rejection covers only that intervention and scope."),
    ],
    "limitations": [
        ("A · ASR", "A 是独立 ASR/RAG 候选注入架构，不应与 B 的直听音频混名。",
         "A is an external ASR/RAG candidate-injection architecture and must not be conflated with B direct audio.",
         "记录 ASR 文本、RAG 候选、注入时刻和实际 call，分别评价召回与执行。",
         "Record ASR text, RAG candidates, injection time, and actual call, scoring recall and execution separately.",
         "ASR 正确不保证工具/参数/车态正确；预取收益需真实流式实现。",
         "Correct ASR does not guarantee tool/argument/state correctness; prefetch gains require true streaming."),
        ("B · pure audio", "B pure 是公平基线：直听 WAV，不发送 SoulX。",
         "B pure is the fair baseline: hear WAV directly and send no SoulX.",
         "固定同一音频 hash、配置、候选授权和回执后，与其他架构同分母比较。",
         "Freeze identical audio hashes, configuration, candidate authorization, and receipts for comparison.",
         "当前 452 没冻结 WAV 且音频运行时生成，严格复现仍缺。",
         "Current 452 has no frozen WAV and synthesizes audio at runtime, so strict reproduction is missing."),
        ("Hybrid C · scoped", "C 合并 direct audio 与 audio-derived ASR/RAG，必须单独命名。",
         "C combines direct audio with audio-derived ASR/RAG and requires a distinct name.",
         "记录 candidate、ASR、SoulX 三条 provenance，禁止读取 manifest q。",
         "Record candidate, ASR, and SoulX provenance; reading manifest q is forbidden.",
         "当前只有冒烟和局部错误桶，且 ASR 先完整转写，不是真流式 C。",
         "Current evidence is smoke and a scoped bucket, with full transcription before playback rather than true streaming C."),
        ("声学与多人", "单音色 clean 无法暴露口音、噪声、双讲和受话对象错误。",
         "Single-voice clean audio cannot expose accent, noise, double-talk, or addressee failures.",
         "冻结多音色/口音、20dB及更强噪声、AEC双讲和多人混音 WAV 与 hash 分桶。",
         "Freeze bucketed multi-voice/accent, 20dB/stronger noise, AEC double-talk, and multi-speaker WAV hashes.",
         "任何运行时重新合成都改变输入分布，不能与旧结果直接合并。",
         "Runtime resynthesis changes the input distribution and cannot merge directly with old results."),
        ("安全与真值", "工具名代理指标看不到参数、位置、危险副作用和最终态。",
         "Tool-name proxies miss arguments, position, dangerous side effects, and final state.",
         "加入 chat 安全集、expected_args、tool+position final state 和真实回读。",
         "Add a chat safety set, expected_args, tool+position final state, and real readback.",
         "当前 CarSim 按 tool 存状态；复杂集只是调用重放，不是车辆事实源。",
         "Current CarSim keys state by tool; complex scoring replays calls and is not a vehicle truth source."),
        ("统计有效性", "单 seed 与标签冲突会让点估计显得比真实证据更确定。",
         "One seed and label conflicts make point estimates look more certain than evidence warrants.",
         "报告 Wilson CI、多 seed、固定 holdout，并让标签冲突双人独立裁决。",
         "Report Wilson intervals, multiple seeds, a frozen holdout, and two-person independent label adjudication.",
         "13 个高置信冲突只给84.51%敏感性上限，另3疑似未经裁决不能改标签。",
         "Thirteen high-confidence conflicts yield only an 84.51% sensitivity ceiling; three suspected cases cannot change labels without adjudication."),
        ("冻结合同", "没有冻结输入与真值就无法判断代码变化还是数据变化导致差异。",
         "Without frozen inputs and truth, code and data changes cannot be disentangled.",
         "版本化 manifest、WAV SHA-256、工具目录、初态、args、final state、阈值和 holdout。",
         "Version manifest, WAV SHA-256, tool catalog, initial state, args, final state, thresholds, and holdout.",
         "Git 当前无 452 WAV/LFS；补齐前只能按受限范围复现。",
         "Git currently has no 452 WAV/LFS; until fixed, reproduction remains scope-limited."),
    ],
    "case-hybrid-c": [
        ("现象", "案例从可观察失败出发，而不是先选论文再寻找问题。",
         "The case starts from observable failures rather than selecting papers before finding a problem.",
         "输入是回执冗长、复杂动作不稳与时延日志；输出是分层错误假设。",
         "Inputs are verbose receipts, unstable complex actions, and latency logs; output is layered failure hypotheses.",
         "现象跨多个机制，不能直接证明某组件有效。",
         "The symptoms span mechanisms and cannot prove any one component."),
        ("实验问题", "问题同时约束收益、真实路径和不可退化项。",
         "The question constrains gain, real path, and non-regression together.",
         "候选合同指定 B/C 基线、样本、开关、指标与 hard gates。",
         "The candidate contract names B/C baseline, samples, switches, metrics, and hard gates.",
         "若基线或音频 provenance 不同，问题不可比较。",
         "Different baseline or audio provenance makes the question incomparable."),
        ("紧凑回执", "缩短成功回执可减少后续 KV 注入成本。",
         "Compact success receipts can reduce subsequent KV injection cost.",
         "只压成功/无需执行，失败回执保留诊断与自救信息。",
         "Only success/idempotent receipts are compacted; failures keep diagnostics and recovery.",
         "组合 e2e 不能归因；仍需 452 单变量回归。",
         "Combination e2e is not attributable; a 452-case ablation remains."),
        ("grouped MoE", "Hopper 的专家分组路径避免大工具块复制与 OOM。",
         "Hopper grouped experts avoid large-tool-block copying and OOM.",
         "运行时按 GPU 能力选择 grouped 或回退实现并记录开关。",
         "Runtime selects grouped or fallback implementation by GPU capability and records it.",
         "硬件限定且组件微基准不能证明端到端准确率。",
         "It is hardware-specific, and a component microbenchmark cannot prove end-to-end accuracy."),
        ("确定性确认", "成功口播必须绑定真实成功/无需执行回执。",
         "Success speech must be bound to a real success/idempotent receipt.",
         "解析结构化回执，失败或未知格式返回模型继续处理而不生成成功确认。",
         "Parse structured receipts; failures or unknown formats return to the model without a success acknowledgment.",
         "它不能替代最终车态回读。",
         "It cannot replace final-state readback."),
        ("Relay", "非承诺前缀降低感知首响但不证明动作完成。",
         "A non-committal prefix lowers perceived first response without proving action completion.",
         "search 意图成立后发送可取消前缀，call 与最终口播另记时钟。",
         "After search intent, send a cancellable prefix while timing call and final speech separately.",
         "1241.6ms 是首音频；call 1818.7ms，车态落地未测。",
         "1241.6ms is first audio; call is 1818.7ms and vehicle-state landing is unmeasured."),
        ("真实 ASR 预取", "C 需要证明候选来自音频而非 manifest 真值。",
         "C must prove candidates derive from audio rather than manifest truth.",
         "保存 ASR raw/corrected text、耗时、规则和 SoulX provenance。",
         "Store raw/corrected ASR text, latency, rules, and SoulX provenance.",
         "当前先完整转写再播放，只是隐藏耗时近似，不是真流式并发。",
         "Current full transcription before playback approximates hidden cost, not true streaming concurrency."),
        ("typed resolver", "候选授权 resolver 收紧模型可执行动作范围。",
         "A candidate-authorized resolver narrows executable model actions.",
         "解析工具、参数和位置，仅允许候选集合，拒绝未知或越权动作。",
         "Parse tool, arguments, and position, allowing only the candidate set and rejecting unknown/unauthorized actions.",
         "31 错误桶收益与 Voice Memory 组合，单组件归因未完成。",
         "The 31-case gain is combined with Voice Memory; single-component attribution is incomplete."),
    ],
}


def enrich_articles(body, slug):
    rules = DETAILS.get(slug, [])
    counter = 0

    def add_detail(match):
        nonlocal counter
        article = match.group(0)
        if "item-detail" in article:
            return article
        counter += 1
        detail = None
        for marker, *content in rules:
            if marker in article:
                detail = detail_block(*content)
                break
        if detail is None:
            detail = detail_block(
                "该条目必须展开输入、运行过程和证据边界，避免一句摘要被误读为已验证结论。",
                "This item expands inputs, execution, and evidence boundaries so a short summary is not mistaken for a verified conclusion.",
                "实现或评测应留下配置、日志、结果范围和可复现链接；页面只展示不含凭据的公开信息。",
                "Implementation or evaluation should leave configuration, logs, result scope, and reproducible links; the page exposes only public, credential-free information.",
                "缺日志、范围不可比或基础设施失败时停止推断；未解决边界保留为待验证项。",
                "Missing logs, incomparable scope, or infrastructure failure stops inference; unresolved boundaries remain pending.")
        opening_end = article.find(">")
        opening = article[:opening_end]
        if " id=" not in opening:
            article = (article[:opening_end]
                       + f' id="{esc(slug)}-item-{counter}"'
                       + article[opening_end:])
        return article[:-10] + detail + "</article>"

    return re.sub(r"<article\b[^>]*>.*?</article>", add_detail, body,
                  flags=re.DOTALL)


def detail_controls():
    return ('<div class="controls detail-controls" role="group" '
            'aria-label="Detailed explanations">'
            '<button class="btn" type="button" onclick="setDetails(true)">'
            + pair("展开全部详细解释", "Expand all details") + "</button>"
            '<button class="btn" type="button" onclick="setDetails(false)">'
            + pair("收起全部详细解释", "Collapse all details") + "</button></div>")


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
summary:focus-visible{outline:3px solid var(--acc);outline-offset:3px;border-radius:4px}
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
.compare.four{grid-template-columns:repeat(4,1fr)}
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
.item-detail{margin-top:12px;background:color-mix(in srgb,var(--card) 82%,var(--chip))}
.item-detail h4{margin:12px 0 3px;font-size:13px;color:var(--fg)}.item-detail p{margin:3px 0}
pre,code{max-width:100%;overflow-wrap:anywhere;white-space:pre-wrap}.detail-controls{position:sticky;
top:6px;z-index:4;background:color-mix(in srgb,var(--bg) 92%,transparent);padding:6px;border-radius:8px}
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
.decision,.compare,.compare.four{grid-template-columns:1fr}.compare .card:after{display:none}.site .sub{display:none}
.evidence-table{display:block;overflow-x:auto}}@media(max-width:480px){
.wrap{padding:12px 12px 48px}.flow{grid-template-columns:1fr}.toolbar{margin-left:0;width:100%}
.hero{padding-top:20px}.navline{grid-template-columns:1fr}.navline a:last-child{text-align:left}
.funnel-row{grid-template-columns:1fr 2fr 42px}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{animation:none!important;
transition:none!important;scroll-behavior:auto!important}.flow-node.pulse:after{display:none}}
@media print{.toolbar,.controls,.navline{display:none!important}details>*{display:block!important}
details:not([open])>*:not(summary){display:block!important}body{background:#fff;color:#000}
.card,details{break-inside:avoid;border-color:#999}}
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
 window.setDetails=function(open){document.querySelectorAll("#main details").forEach(
   function(item){item.open=!!open})};
 function openHash(){if(!location.hash)return;var target=document.getElementById(
   decodeURIComponent(location.hash.slice(1)));if(!target)return;
   target.querySelectorAll("details").forEach(function(item){item.open=true});
   var parent=target.closest("details");if(parent)parent.open=true}
 window.addEventListener("hashchange",openHash);openHash();
 document.addEventListener("keydown",function(e){if(e.key==="Escape")window.resetFlow()});
})();
"""


def header():
    return f"""<header class="site">
<a class="brand" href="{BASE}/">🚗 cockpit-agent-radar</a>
<span class="sub">{pair("自动化系统讲解","automation system guide")}</span>
<nav class="toolbar" aria-label="Site">
<a class="btn" href="{BASE}/automation/">{pair("自动化","Automation")}</a>
<a class="btn" href="{BASE}/solutions/">{pair("好方案","Solutions")}</a>
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


def shell(title_zh, title_en, slug, body, snapshot=None, enrich=True):
    snapshot = snapshot or empty_snapshot()
    if enrich:
        body = enrich_articles(body, slug)
        body = body.replace("</section>", "</section>" + detail_controls(), 1)
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
              f'<span class="badge verified">{pair("8/8–8/9 闭环：已完成","Aug 8–9 loop: closed")}</span>')
    body = hero("从技术雷达到可验证改进", "From radar to verified improvements",
        "这不是“让模型自动改代码”一个动作，而是一条有证据、有隔离、有硬门、可回滚的闭环。点击节点看输入、输出、失败边界与责任归属。",
        "This is not one “let a model edit code” action. It is an evidence-backed, isolated, gated, reversible loop. Open any node for inputs, outputs, and failure boundaries.", badges)
    ledger_rows = []
    labels = {
        "fulltext_review": "精读", "problem_report": "日报",
        "duplex_report": "全双工", "candidate_publish": "候选",
        "candidate_ack": "ACK", "offline_replay": "离线",
        "h20_evaluation": "H20", "result_manifest": "结果",
        "radar_writeback": "回写",
    }
    for row in snapshot.get("ledger_days", []):
        statuses = " · ".join(
            f"{labels.get(stage, stage)}={status}"
            for stage, status in row["stages"].items())
        ledger_rows.append(
            f'<li><b>{esc(row["date"])}</b> · {esc(statuses)}</li>')
    ledger_html = (
        "<ul>" + "".join(ledger_rows) + "</ul>"
        if ledger_rows else f"<p>{pair('尚无 handoff ledger','No handoff ledger yet')}</p>")
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
<article class="card"><h3 class="verified">{pair("已闭环：8月8–9日补跑","Closed: Aug 8–9 catch-up")}</h3><p>{pair("两个候选均在离线门终止并回写；下一次 02:00 从缺失日期扫描开始，不会重复精读、候选或同 candidate/commit 实验。","Both candidates terminated at the offline gate and were written back. The next 02:00 run starts with missing-date scanning and will not repeat reviews, candidates, or the same candidate/commit experiment.")}</p></article>
</div></section>
<section class="section"><h2>{pair("按日期闭环状态","Daily closed-loop status")}</h2>
<div class="card">{ledger_html}<p class="sub">{pair(
    "missing/pending/failed/stale 都是显式未完成；只有 complete/rejected/not_applicable 是终态。",
    "missing/pending/failed/stale are explicit non-terminal states; only complete/rejected/not_applicable are terminal.")}</p></div></section>
<section class="section"><h2>{pair("实验反馈回到下一轮","Experiment feedback closes the loop")}</h2>
<div class="card"><p>{pair(
    f"当前公开 {snapshot.get('solution_count', 0)} 个严格筛选的保留/条件保留组件。日报读取实验 registry，组件页保存证据范围与下一验证门，再反馈候选生成；数据源状态：{snapshot.get('solution_status','stale')}。",
    f"{snapshot.get('solution_count', 0)} strictly selected retained/conditional components are public. Reports read the experiment registry; solution pages preserve evidence scope and next gates before feeding candidate generation. Source status: {snapshot.get('solution_status','stale')}.")}</p>
<p><a class="btn" href="{BASE}/solutions/">{pair("查看高收益组件 →","Open high-value solutions →")}</a></p></div></section>
<p class="callout ok"><b>{pair("完整案例：","Full case:")}</b> <a href="{BASE}/automation/case-hybrid-c/">{pair("Hybrid C 为什么在 452 全量前只能局部留存 →","Why Hybrid C remains scoped before a full 452-case run →")}</a></p>"""
    return shell("自动化系统总览", "Automation overview", "research", body, snapshot,
                 enrich=False).replace(
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
    queued_reviews = int(
        snapshot.get("cost_status", {}).get("queued_fulltext_papers", 0) or 0)
    cost_baseline = snapshot.get("cost_status", {}).get("dashboard_baseline") or {}
    baseline_totals = cost_baseline.get("totals", {})
    baseline_targets = cost_baseline.get("targets", {})
    baseline_driver = cost_baseline.get("primary_cost_driver") or {}
    body = hero("论文调研", "Research",
        "调研层先用确定性脚本扩大召回，再让 Cursor 只处理值得全文精读的证据；“摘要速读”和“正文精读”在页面上明确分级。",
        "Deterministic scripts maximize recall; Cursor spends time only on evidence worth full-text review. Abstract briefs and full-text reviews remain visibly distinct.",
        '<span class="badge mixed">Mixed ownership</span><span class="badge script">Fetch/score: scripts</span><span class="badge cursor">Full text: Cursor</span><span class="badge verified">1 full-text run/day</span>')
    body += f"""<section class="section"><h2>{pair("当前真实数据","Current live data")}</h2>
<div class="metrics">
<div class="metric"><b>{metric_value(snapshot, "total_items")}</b><small>{pair("总收录条目","collected items")}</small></div>
<div class="metric"><b>{metric_value(snapshot, "paper_count")}</b><small>{pair("有效论文数","valid papers")}</small></div>
<div class="metric"><b>{metric_value(snapshot, "fulltext_count")}</b><small>{pair("editorial + fulltext 精读","editorial + fulltext reviews")}</small></div>
<div class="metric"><b>{metric_value(snapshot, "abstract_count")}</b><small>abstract_backfill</small></div>
<div class="metric"><b>{queued_reviews}</b><small>{pair("因每日成本/数量上限排队的 canonical 精读","canonical reviews queued by daily cost/count cap")}</small></div>
<div class="metric"><b>{metric_value(snapshot, "history_count")}</b><small>{pair("review history 有效记录","valid review-history records")}</small></div>
<div class="metric"><b>{esc(snapshot.get("latest_review_date") or "—")} · {snapshot.get("latest_review_count", 0) if snapshot.get("latest_review_date") else "—"}</b><small>{pair("最新精读日期 · 当天数量","latest review date · count")}</small></div>
</div>
<p class="sub">{pair(
    "定义：收录仅计 items.json 的对象；有效论文为其中 kind=paper 且 ID 可发布的条目；正文精读来自 explanations.json 的 editorial+fulltext；摘要速读仅计 abstract_backfill；历史记录还须关联有效论文且状态、深度和日期合法。镜像只在链接列表合并，不篡改原始记录计数。构建时间：",
    "Definitions: collected counts object rows in items.json; valid papers have kind=paper and a publishable ID; full-text reviews are editorial+fulltext in explanations.json; abstract briefs count only abstract_backfill; history records must also reference a valid paper with valid status, depth, and date. Mirrors are merged only in the link list, without altering source-record counts. Built:")} {esc(snapshot["build_time"])}</p>
</section>
<section class="section"><h2>{pair("真实成本基线与目标","Observed cost baseline and targets")}</h2>
<div class="metrics">
<div class="metric"><b>${float(baseline_totals.get("completed_days_average_cost_usd", 0)):.2f}</b><small>{pair("8/4–8/9 完整日均","Aug 4–9 complete-day average")}</small></div>
<div class="metric"><b>{float(baseline_targets.get("reduction_to_soft_pct", 0)):.2f}%</b><small>{pair("降至 $100 soft 所需降幅（3.73倍）","reduction required for $100 soft (3.73x)")}</small></div>
<div class="metric"><b>{float(baseline_targets.get("reduction_to_hard_pct", 0)):.2f}%</b><small>{pair("降至 $120 hard 所需降幅（3.11倍）","reduction required for $120 hard (3.11x)")}</small></div>
<div class="metric"><b>{float(baseline_driver.get("share", 0)) * 100:.2f}%</b><small>{esc(baseline_driver.get("model") or "unknown")} {pair("历史费用占比","historical cost share")}</small></div>
</div>
<p class="callout">{pair(
    "Dashboard 共计 $2,537.67、1.838B tokens、585 calls；历史包含手工聊天/子 Agent 和自动化，且没有 pipeline/stage 标签，不能精确归因。medium 占 83.89%，首要措施是减少调用和上下文并把 Radar 迁到 Included Composer，而不是只压缩 xhigh。",
    "Dashboard totals are $2,537.67, 1.838B tokens, and 585 calls. History mixes manual chats/subagents with automation and has no pipeline/stage labels, so exact historical attribution is impossible. Medium drove 83.89%; the primary controls are fewer calls, smaller contexts, and moving Radar to included Composer—not only reducing xhigh.")}</p>
<p class="sub">{pair("本地 $120 门只约束计划任务；手工聊天和手工子 Agent 不受本地调度器控制，仍必须设置账户级 spend limit。","The local $120 gate covers scheduled tasks only. Manual chats and manual subagents remain outside the local scheduler, so an account-level spend limit is still required.")}</p>
</section>
<section class="section"><h2>{pair("动态调研漏斗","Live research funnel")}</h2><div class="card funnel">{funnel(snapshot)}</div></section>
<section class="section"><h2>{pair("查看真实产物","Open real artifacts")}</h2><div class="card artifacts">{artifact_links(snapshot)}</div></section>
<section class="section"><h2>{pair("严格 B 基线审计更正","Strict B-baseline audit correction")}</h2>
<div class="audit-banner">{pair("论文调研进入候选前必须绑定正确的架构与证据口径。B pure 是 Qwen 直听音频且不发送 SoulX 文本；B + 真实 SoulX 是从 WAV 完整转写后注入 audio-derived text 的独立变体；manifest 原文注入只能是 assisted_diagnostic。当前自动化默认 asr_prefetch=true，因此测试的是 audio-derived C 路径，不是严格 B pure 基线。",
"Research must bind each candidate to the correct architecture and evidence scope. B pure lets Qwen hear audio directly and sends no SoulX text. B + real SoulX is a separate variant that fully transcribes the WAV before injecting audio-derived text. Manifest-transcript injection is assisted_diagnostic only. Current automation defaults asr_prefetch=true, so it exercises an audio-derived C path, not the strict B pure baseline.")}</div>
<div class="grid">
<article class="card"><h3>{pair("452 合法指标","Valid 452 metric")}</h3><p><b>369 / 452 = 81.64%</b> · Wilson CI 77.81–84.93%</p><p>{pair("准确名称：单音色 clean 合成语音下 expected-tool successful-or-idempotent receipt rate。它不是端到端任务成功率；其中 49 个成功只靠“无需执行”，必须与物理执行分开。",
"Exact name: expected-tool successful-or-idempotent receipt rate under single-voice clean synthetic speech. It is not end-to-end task success. Forty-nine successes rely only on an “already satisfied/no execution” receipt and must be separated from physical execution.")}</p></article>
<article class="card"><h3>{pair("音频与标签敏感性","Audio and label sensitivity")}</h3><p>{pair("427 条运行时 Edge TTS、23 条索引精确匹配、2 条合成失败；全部为单音色、clean、single-turn，Git 不含 452 WAV/LFS，也没有冻结 WAV hash。至少 13 条高置信语义等价/标签冲突只把敏感性上限推到 84.51%；再加 3 条疑似也仅 85.18%，且未经双人裁决不能改标签。",
"427 used runtime Edge TTS, 23 exact index matches, and two synthesis failures. All are single-voice, clean, single-turn; Git contains no 452 WAV/LFS and no frozen WAV hash. At least 13 high-confidence semantic-equivalence/label conflicts raise only a sensitivity ceiling of 84.51%; adding three suspected cases reaches 85.18%, and no label may change without two-person adjudication.")}</p></article>
</div>
<p class="sub">{pair("这些是对现有代码、manifest 和结果的只读审计结论；本站没有把它冒充为单独发布的 GitHub 审计文件。代码证据入口见 Selection 与 Limitations。",
"These are read-only audit conclusions from existing code, manifest, and results. This site does not present them as a separately published GitHub audit file. Selection and Limitations link the underlying code evidence.")}</p>
<p><a href="{BASE}/automation/selection/">{pair("查看严格选择门 →","Open strict selection gates →")}</a> · <a href="{BASE}/automation/limitations/">{pair("查看公平矩阵与必须立刻修复项 →","Open the fairness matrix and immediate fixes →")}</a></p></section>
<section class="section"><h2>{pair("从四源到站内证据","From four sources to site evidence")}</h2><div class="steps">
<article class="step"><h3>arXiv / GitHub / Hugging Face / Hacker News</h3><p>{pair("按源抓取，统一成 title、URL、来源、发布时间、分数和标签；陌生仓库只读官方材料，不执行代码。","Source adapters normalize title, URL, source, date, score, and tags. Unknown repositories are inspected, never executed.")}</p></article>
<article class="step"><h3>{pair("关键词评分与去重","Scoring and deduplication")}</h3><p>{pair("标题命中加权；既有 URL 先更新再应用新条目上限。同题镜像通过 canonical_id / mirror_of 合并，重试保持幂等。","Title matches receive extra weight. Existing URLs update before the new-item cap. Mirrors use canonical_id / mirror_of; retries stay idempotent.")}</p></article>
<article class="step"><h3>{pair("零模型摘要回填","Model-free abstract backfill")}</h3><p>{pair("GitHub Actions 用摘要生成明确标注的速读，Cursor 缺席时仍可发布；它不计入正文精读历史。","Actions generates a clearly labeled abstract brief, so publishing does not depend on Cursor. It does not count as full-text review.")}</p></article>
<article class="step"><h3>{pair("Cursor 全文精读","Cursor full-text review")}</h3><p>{pair("读取论文正文、官方项目页、仓库和模型页，补问题、方法、流程、结果、局限、开放状态以及对 Harness 的编辑判断。","Cursor reads the paper and official project, repository, and model pages, adding problem, method, workflow, findings, limits, openness, and editorial fit.")}</p></article>
<article class="step"><h3>review_history.json</h3><p>{pair("只有 editorial + fulltext 的状态迁移才入历史；北京时间、来源、详情页和 automation run 可核验。","Only an editorial + fulltext transition enters history, with Beijing time, source, detail route, and automation run.")}</p></article>
</div></section>
<section class="section"><h2>{pair("失败不是静默成功","Failure is not silent success")}</h2><div class="grid">
<article class="card"><h3>{pair("定时","Schedule")}</h3><p>{pair("无 Agent 的 GitHub 抓取保留 09:00 / 14:00 / 19:00；本地全文精读仅 20:00 一次，每日最多6篇 canonical 论文。","Agent-free GitHub fetches remain at 09:00 / 14:00 / 19:00; local full-text review runs once at 20:00, capped at six canonical papers/day.")}</p></article>
<article class="card"><h3>{pair("重试与锁","Retry and locking")}</h3><p>{pair("本地任务共享原子 PID 锁；Cursor 最多两次尝试且重试复用同一 chat。","Local tasks share an atomic PID lock. Cursor gets at most two attempts and retries resume the same chat.")}</p></article>
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
    queued_candidates = int(
        snapshot.get("cost_status", {}).get("queued_harness_candidates", 0) or 0)
    body = hero("实验候选与隔离实现", "Candidates and isolated implementation",
        "把日报建议拆成一次只改变一个机制的候选。Cursor Agent 可以写代码，但不能改真值、降低阈值或在共享工作树里覆盖别人的实验。",
        "Report advice is decomposed into candidates that change one mechanism at a time. Cursor may write code, but cannot edit truth, lower thresholds, or overwrite another experiment.",
        '<span class="badge cursor">Cursor Agent implementation</span><span class="badge verified">Worktree isolation</span>')
    latest_day = max(snapshot.get("experiment_days", {}), default="")
    activities = snapshot.get("experiment_days", {}).get(
        latest_day, {}).get("activities", [])
    cards = []
    for row in activities:
        status = esc(row.get("status", "invalid"))
        link = next((url for url in row.get("source_links", [])
                     if isinstance(url, str) and url.startswith("https://")), "")
        cards.append(
            f'<article class="card"><h3>{esc(row.get("name") or row.get("id"))}'
            f' · <span class="badge {status}">{status}</span></h3>'
            f'<p>{esc(row.get("problem") or "未记录")}</p>'
            f'<p>baseline={esc(row.get("baseline_id") or "preliminary")} · '
            f'{esc(row.get("single_variable") or "未记录")}</p>'
            f'<p>{esc(row.get("reason") or "未记录")}</p>'
            + (f'<a href="{esc(link)}">{pair("分支/来源","Branch/source")}</a>'
               if link else "") + "</article>")
    body += f"""<section class="section"><h2>{pair("四层状态模型","Four separate state layers")}</h2><div class="grid">
<article class="card"><h3>candidate / evidence pool</h3><p>{pair("只要绑定可比基线或明确离线范围、单变量、指标和复现信息即可进入；缺基线标 preliminary。",
"Admission needs a comparable baseline or explicit offline scope, one variable, metrics, and reproduction; missing baselines are preliminary.")}</p></article>
<article class="card"><h3>offline compared / component candidate</h3><p>{pair("+1、+4 且成功集零退化也可条件保留并进入组合队列；负收益留作 negative evidence，不进入执行队列。",
"Even +1 or +4 with zero regression may be conditionally retained and composed; negative evidence is archived but not executed.")}</p></article>
<article class="card"><h3>H20 eligible</h3><p>{pair("当前最佳434/452、目标448/452，动态 gap=14。小收益先 smoke/quick/targeted，不被固定16挡在研究入口。",
"Current best is 434/452 and target 448/452, so the dynamic gap is 14. Smaller gains use smoke/quick/targeted first.")}</p></article>
<article class="card"><h3>qualified</h3><p>{pair("只有 full、complex、时延、安全及同口径零退化硬门全部通过才能使用；不能由局部数字相加得到。",
"Qualified requires every full, complex, latency, safety, and zero-regression gate; local gains cannot simply be added.")}</p></article>
</div></section>
<section class="section"><h2>{pair("候选实验室","Candidate laboratory")} · {esc(latest_day)}</h2>
<p class="callout">{pair("因每日成本/数量上限排队的 Harness 候选：","Harness candidates queued by the daily cost/count cap:")} <b>{queued_candidates}</b></p>
<p class="callout">{pair("Solutions 只展示正式保留；这里展示 proposed、offline compared、conditional component、H20 eligible、qualified、rejected/invalid。",
"Solutions shows retained work only; this lab includes proposed through rejected/invalid states.")}</p>
<div class="grid">{"".join(cards) or pair("research_exhausted：无可行候选，但精读/筛选计数已记录。","Research exhausted; review and screening counts remain recorded.")}</div></section>
<section class="section"><h2>{pair("候选合同","Candidate contract")}</h2><div class="steps">
<article class="step"><h3>{pair("先写假设","State one hypothesis")}</h3><p>{pair("例：确定性确认可修复确认语句，不改变生成模型；typed resolver 只负责结构化动作消歧。","Example: deterministic confirmation fixes confirmations without changing generation; typed resolver only disambiguates structured actions.")}</p></article>
<article class="step"><h3>{pair("独立 worktree","Isolated worktree")}</h3><p>{pair("每个候选有自己的分支、依赖和运行目录；实现失败可直接丢弃，不污染基线。","Each candidate gets its own branch, dependencies, and runtime directory. A failed implementation can be discarded without contaminating baseline.")}</p></article>
<article class="step"><h3>{pair("保护真值与门槛","Protect truth and gates")}</h3><p>{pair("禁止改测试期望、删除难例、放宽 99% / 1.6s 门槛或用缓存答案伪造命中。","Do not alter expectations, remove hard cases, relax 99% / 1.6s, or fake hits with answer caching.")}</p></article>
<article class="step"><h3>{pair("登记可组合组件","Register composable components")}</h3><p>{pair("Typed Action、Voice Memory、紧凑回执、安全前缀等按组件登记，便于之后组合，而不是把一次实验写成不可拆的补丁。","Typed Action, Voice Memory, compact receipts, and safety prefixes are registered as components for later composition, not one inseparable patch.")}</p></article>
</div></section>
<section class="section"><h2>{pair("为什么强调单变量","Why single-variable candidates")}</h2><p class="callout bad">{pair("多个机制一起变化即使指标上升，也无法知道谁有效；指标下降时更无法安全回退。组合候选只能在各组件已有独立证据后进入。","If several mechanisms change together, neither gains nor regressions are attributable. Combination candidates enter only after each component has independent evidence.")}</p></section>
<section class="section"><h2>complex_control_cases v2</h2><p class="callout">{pair("实验分支 canary 已通过：full 434/452 零退化、complex strict 43/122，因此仅 safe_partial_improvement，不是 qualified；正式 v1 结果未改。",
"The experiment branch passed the full canary with 434/452 preserved, but complex strict is 43/122, so it is a safe partial improvement, not qualified; formal v1 results remain untouched.")}</p>
<p><a href="https://github.com/ISS-2030Lab/StreamingModelHarness/tree/experiment/complex-v2-fair-ab-20260809">{pair("打开实验分支","Open experiment branch")}</a></p></section>
<p><a href="{BASE}/automation/case-hybrid-c/#candidate">{pair("案例关联：Hybrid C 的六个组件怎样逐步进入 →","Case link: how six Hybrid C components entered →")}</a></p>
<p><a href="{BASE}/automation/limitations/">{pair("证据审计：组合组件如何归因、哪些结论仍不能说 →","Evidence audit: component attribution and claims not yet supported →")}</a></p>"""
    return shell("实验候选", "Candidates", "candidates", body, snapshot)


def h20(snapshot=None):
    snapshot = snapshot or empty_snapshot()
    body = hero("双 GPU H20 隔离评测", "Dual-GPU H20 evaluation",
        "评测把基线与候选放在两个独立 worker，先做便宜的失败筛查，再逐级扩大到真实音频与复杂意图。",
        "Baseline and candidate run in separate workers. Cheap failures are filtered first, then scope expands to real audio and complex intent.",
        '<span class="badge script">Deterministic runner</span><span class="badge pending">Next 02:00 resume pending</span>')
    body += f"""<section class="section"><h2>{pair("资源拓扑","Resource topology")}</h2><div class="grid">
<article class="card"><h3>Worker A · GPU 4/5</h3><p>{pair("基线或候选 A；188xx 端口段。CUDA 可见设备和服务 PID 明确记录。","Baseline or candidate A; 188xx port range. CUDA visibility and service PIDs are recorded.")}</p></article>
<article class="card"><h3>Worker B · GPU 6/7</h3><p>{pair("候选或复验；189xx 端口段。端口、进程、日志与 worktree 不共享。","Candidate or confirmation; 189xx port range. Ports, processes, logs, and worktree are not shared.")}</p></article>
</div></section>
<section class="section"><h2>{pair("由小到大的评测漏斗","Evaluation funnel")}</h2><div class="steps">
<article class="step"><h3>Smoke</h3><p>{pair("验证服务可启动、协议完整、关键动作能走通；失败立即停止。","Verify startup, protocol integrity, and critical actions; stop immediately on failure.")}</p></article>
<article class="step"><h3>452 {pair("条组合集","combination set")}</h3><p>{pair("覆盖能力组合和回归；同时报告组合完成率与工具执行率，不能用一个数字替代另一个。","Covers capability combinations and regressions. Combined completion and tool execution are reported separately.")}</p></article>
<article class="step"><h3>122 {pair("条复杂意图","complex intents")}</h3><p>{pair("只有前层通过才扩大到多约束、指代、确认与安全边界。","Only survivors expand to multi-constraint, reference, confirmation, and safety cases.")}</p></article>
<article class="step"><h3>{pair("真实音频 profile：B pure 与 audio-derived C","Real-audio profiles: B pure and audio-derived C")}</h3><p>{pair("B pure 只让模型直听音频、不发送 SoulX；C 才记录从 WAV 得到的 ASR/SoulX provenance。manifest 原文注入只能 assisted_diagnostic。当前默认 asr_prefetch 测 C，不能替代 B pure。","B pure lets the model hear audio directly and sends no SoulX; C records ASR/SoulX provenance derived from the WAV. Manifest transcript injection is assisted_diagnostic only. Current default asr_prefetch tests C and cannot replace B pure.")}</p></article>
</div></section>
<section class="section"><h2>{pair("时延与清理","Latency and cleanup")}</h2><div class="grid">
<article class="card"><h3>e2e P95</h3><p>{pair("当前口径是 commit 到 Relay 首音频包，不是工具 call 或车态落地；1241.6ms 与 call P95 1818.7ms 必须同时展示。0.7s VAD 仅为 runner 元数据，未真实等待。","Current scope is commit to Relay first audio, not tool call or vehicle-state landing; 1241.6ms must be shown beside call P95 1818.7ms. The 0.7s VAD is runner metadata and is not actually waited.")}</p></article>
<article class="card"><h3>{pair("安全清理","Safe cleanup")}</h3><p>{pair("只按启动记录中的 PID 与端口清理；校验归属后终止。禁止模糊匹配杀进程，失败也执行 finally 清理。","Clean only recorded PIDs and ports after ownership checks. No broad process matching; finally cleanup runs after failures.")}</p></article>
</div></section>
<div class="callout"><b>{pair("证据声明：","Evidence statement:")}</b> {pair("该隔离方案和手动案例数据可核验；8月9日恢复点是 offline_replay，下一次 02:00 接续尚未发生，不能声称已稳定无人值守运行。","The isolation design and manual case data are verifiable. The Aug 9 recovery point is offline_replay; the next 02:00 resume has not happened, so stable unattended operation is not claimed.")}</div>
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
<p class="callout"><b>{pair("源码核对后的缺口：","Source-audited gaps:")}</b> {pair("当前默认 commit_to_call P95 门为 None，真正启用时才成为 research 硬门；评分源码已有参数/最终态 production 门，但历史 452 registry 只有工具执行代理指标、复杂集 not_run，且 2 条基础设施错误仍在记录中。更关键的是自动化 H20 默认 asr_prefetch=true：它测试 audio-derived C 变体，不是“不带 SoulX”的 B pure，绝不能拿来替代 B 基线。",
"The default commit_to_call P95 target is None and becomes a research gate only when configured. Scoring source already has production parameter/final-state gates, but the historical 452 registry contains only a tool-execution proxy, complex suite not_run, and two recorded infrastructure errors. More importantly, H20 automation defaults asr_prefetch=true: it tests an audio-derived C variant, not B pure without SoulX, and can never substitute for that B baseline.")}</p></section>

<section class="section"><h2>{pair("可交互决策树","Interactive decision tree")}</h2>
<p class="sub">{pair("点击或用 Tab 聚焦后按 Enter/Space 展开每道门；原生 details 控件无需脚本，减少动态效果设置同样生效。","Click, or focus with Tab and press Enter/Space, to expand each gate. Native details need no script and respect reduced-motion settings.")}</p>
<div class="decision-tree" role="tree" aria-label="候选选择决策树 Candidate selection decision tree">
<details id="selection-gate-validity" role="treeitem"><summary tabindex="0">{pair("基础设施与口径有效？否 → invalid","Infrastructure and scope valid? No → invalid")}</summary><p>{pair("输入：profile、stage、manifest audit、sample_id 映射、unknown ID、音频来源、服务/端口/GPU/TTS 错误、结果文件与哈希。pure_audio 禁止 assisted_text、manifest 原文或 truth_text_preinjected 捷径。","Inputs: profile, stage, manifest audit, sample-ID mapping, unknown IDs, audio provenance, service/port/GPU/TTS errors, result files, and hashes. pure_audio forbids assisted_text, manifest transcript, or truth_text_preinjected shortcuts.")}</p></details>
<details id="selection-gate-safety" role="treeitem"><summary tabindex="0">{pair("安全门通过？否 → rejected","Safety gate passes? No → rejected")}</summary><p>{pair("输入：dangerous_miscalls=0、chit_chat_miscall_rate≤1%、闲聊样本存在、每个 call 在候选授权集合内、真实执行证据存在。口径无效优先 invalid；有效但安全退化才 rejected。","Inputs: dangerous_miscalls=0, chit_chat_miscall_rate≤1%, chat samples present, every call within candidate authorization, and real execution evidence. Invalid scope takes precedence; valid evidence with a safety regression is rejected.")}</p></details>
<details id="selection-gate-baseline" role="treeitem"><summary tabindex="0">{pair("相对同口径基线有收益？否 → rejected","Benefit over like-for-like baseline? No → rejected")}</summary><p>{pair("输入：baseline_id、profile、样本/分桶、完成率、actual_execution_success_rate、e2e P95 与 delta。样本范围不同、映射无效或必需指标缺失时不是“无收益”，而是 invalid。","Inputs: baseline_id, profile, sample/buckets, completion, actual_execution_success_rate, e2e P95, and delta. Different scope, invalid mapping, or missing required metrics means invalid, not “no gain.”")}</p></details>
<details id="selection-gate-qualification" role="treeitem"><summary tabindex="0">{pair("全部研究/生产硬门通过？是 → qualified","All research/production hard gates pass? Yes → qualified")}</summary><p>{pair("输入：smoke、full≥452、分桶、完成、安全、严格执行、e2e、复杂集、基线不退化；生产层再读 truth_coverage 与 task_success_rate。qualified 必须注明是 research 还是 production 资格。","Inputs: smoke, full≥452, buckets, completion, safety, strict execution, e2e, complex suite, and no baseline regression; production additionally reads truth_coverage and task_success_rate. qualified must state whether it is research or production eligibility.")}</p></details>
<details id="selection-gate-partial" role="treeitem"><summary tabindex="0">{pair("未过全部门但有收益？→ pareto 或 partial_improvement","Some gain but not all gates? → pareto or partial_improvement")}</summary><p>{pair("当前 registry.classify_result 对未 qualified 且安全、可比、有质量/时延收益的候选分类：若位于前沿则 pareto，否则 partial_improvement。二者都不是 production eligible；只有可归因组件才能进入 retained/conditional。",
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
<article class="card"><h3>accuracy / truth</h3><p>{pair("research 严格执行要求 expected tool 与真实 call 对齐，且 execution evidence 覆盖100%；production 再要求参数合法、期望最终态与实际最终态一致。当前 369/452 只能叫 expected-tool successful-or-idempotent receipt rate；49 条仅“无需执行”，物理执行必须另列。","Research strict execution aligns expected tool with a real call and requires 100% execution-evidence coverage. Production adds legal parameters and expected-versus-actual final state. The current 369/452 is only the expected-tool successful-or-idempotent receipt rate; 49 are idempotent-only and physical execution must be separate.")}</p></article>
<article class="card"><h3>latency</h3><p>{pair("e2e 是 commit→Relay 首音频 P95；call P95 单列。1241.6ms 可过首响门，但 call 是 1818.7ms，车态落地未测。0.7s VAD 只是 runner 元数据，当前没有真实等待。","e2e is commit→Relay first-audio P95; call P95 is separate. 1241.6ms passes first response while call is 1818.7ms and state landing is unmeasured. The 0.7s VAD is runner metadata only and is not actually waited.")}</p></article>
<article class="card"><h3>complex / multiturn</h3><p>{pair("research 需要 122 复杂意图套件结果，默认目标≥95%，并覆盖 single_turn/multi_turn。合成复杂集只能补结构难度，不能替代真实车内分布。","Research requires the 122-case complex-intent result with default target ≥95% and both single_turn/multi_turn buckets. A synthetic complex suite adds structural difficulty but does not replace real in-car distribution.")}</p></article>
<article class="card"><h3>baseline / delta</h3><p>{pair("基线必须 mapping_valid、profile 一致、包含完成/实际执行/e2e 必需指标，并在相同样本与分桶比较；任何完成、严格执行或 e2e 退化都会阻断资格。多 seed 和置信区间尚未成为当前源码硬门，是明确待补缺口。","Baseline must be mapping_valid, profile-matched, include completion/actual-execution/e2e metrics, and use the same samples and buckets. Regression in completion, strict execution, or e2e blocks eligibility. Multiple seeds and confidence intervals are not yet source hard gates and remain explicit gaps.")}</p></article>
</div></section>

<section class="section"><h2>{pair("整套方案留存 vs 子组件留存","Whole-candidate vs component retention")}</h2>
<div class="grid"><article class="card"><h3>{pair("整套候选","Whole candidate")}</h3><p>{pair("只有明确资格层的全部硬门通过，才可写 qualified。pareto/partial 的实验分支用于复现和消融，不自动进默认组合、不合并 main。","Only passing every gate for a named tier permits qualified. Pareto/partial experiment branches exist for reproduction and ablation; they do not enter the default composition or merge main automatically.")}</p></article>
<article class="card"><h3>{pair("可归因子组件","Attributable component")}</h3><p>{pair("组合未过门时，组件只有在单测、微基准、消融或明确局部错误桶能归因时才可标 retained/conditional。组合共享 e2e 不能拆给每个组件；无收益组件保持 rejected。","When a combination fails, a component becomes retained/conditional only with attributable unit, microbenchmark, ablation, or scoped-bucket evidence. Shared combination e2e cannot be assigned to each component; no-gain components remain rejected.")}</p></article></div>
<div class="legend"><a class="btn" href="{retained_json}">retained_components.json</a><a class="btn" href="{retained_md}">RETAINED_COMPONENTS.md</a><a class="btn" href="{registry}">experiment registry.json</a></div></section>
<p><a class="btn" href="{BASE}/solutions/">{pair("查看公开组件介绍页","Open public component pages")}</a></p>

<section class="section"><h2>{pair("当前三张判定卡","Three current verdict cards")}</h2><div class="grid">
<article class="card verdict warn"><h3>B pure-audio · 452 · partial_improvement</h3><div class="metrics"><div class="metric"><b>99.56%</b><small>completion</small></div><div class="metric"><b>369 / 452</b><small>81.64% · Wilson CI 77.81–84.93%</small></div><div class="metric"><b>1241.6ms</b><small>commit→Relay first audio</small></div><div class="metric"><b>1818.7ms</b><small>call P95</small></div></div><p>{pair("合法指标是单音色 clean 合成语音下 expected-tool successful-or-idempotent receipt rate；其中 49 条只靠无需执行。2 条 infrastructure errors；复杂集 not_run。它不是端到端任务成功率，registry 结论是 partial_improvement，不是 qualified。","The valid metric is expected-tool successful-or-idempotent receipt rate under single-voice clean synthetic speech; 49 are idempotent-only. There are two infrastructure errors and complex is not_run. This is not end-to-end task success; registry verdict is partial_improvement, not qualified.")}</p><a href="{registry}">{pair("查看 registry 原记录","Open source registry record")}</a></article>
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
<article class="step"><h3>registry + retained components</h3><p>{pair("记录配置、提交、数据范围、指标、状态、错误桶和负结果；partial 只登记被保留的组件与适用边界。安全快照同步后生成公开 Solutions 详情与每日变更页。","Record config, commit, scope, metrics, status, error buckets, and negative results. Partial entries name only retained components and boundaries. A sanitized snapshot then builds public Solutions detail and daily-change pages.")}</p><p><a href="{BASE}/solutions/">{pair("查看公开组件索引","Open public solutions index")}</a></p></article>
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

<section class="section"><h2>{pair("公平 A / B / B+SoulX / C 矩阵","Fair A / B / B+SoulX / C matrix")}</h2>
<div class="compare four">
<article class="card"><h3>A · ASR / RAG</h3><p>{pair("真实 ASR 后做 RAG 候选召回与晚注入；其预取思想进入 C，但 A 本身仍作为独立基线保留。","Real ASR followed by RAG candidate recall and late injection. Its prefetch path informs C, while A remains an independent baseline.")}</p></article>
<article class="card"><h3>B · pure audio</h3><p>{pair("Qwen 直听音频，不发送 x_soulx_text；这是严格 B pure 基线。当前组合固定 grouped MoE、紧凑回执、确定性确认与 Relay，但不能偷偷加入 ASR 文本。","Qwen hears audio directly and sends no x_soulx_text; this is the strict B pure baseline. The current combination fixes grouped MoE, compact receipts, deterministic confirmation, and Relay, but cannot add ASR text silently.")}</p></article>
<article class="card"><h3>B + {pair("真实 SoulX","real SoulX")}</h3><p>{pair("直听音频同时注入从同一 WAV 得到的 audio-derived ASR 文本；是独立变体。manifest 原文模拟只能标 assisted_diagnostic，永远不可晋级。","Direct audio plus audio-derived ASR text from the same WAV is a separate variant. Manifest-transcript simulation is assisted_diagnostic and can never promote.")}</p></article>
<article class="card"><h3>Hybrid C · audio-derived</h3><p>{pair("组合 A 的真实 ASR/RAG 候选与 B 的直听音频、回执和 typed action。当前 asr_prefetch 先完整转写再播放，只是耗时隐藏近似；4/4 冒烟与 24/31 局部证据不能外推。",
"Combines A's real-ASR/RAG candidates with B's direct audio, receipts, and typed actions. Current asr_prefetch fully transcribes before playback and only approximates hidden cost; 4/4 smoke and 24/31 scoped evidence do not extrapolate.")}</p></article>
</div>
<p class="callout bad">{pair("禁止表述：“Hybrid C 在 452 条上达到 99.56%”或“Hybrid C 已达到 99%”。前者把 B 的结果错挂到 C，后者把 4 条冒烟或错误桶修复外推为总体准确率。",
"Prohibited claims: “Hybrid C reached 99.56% on 452 cases” or “Hybrid C has reached 99%.” The first assigns B's result to C; the second extrapolates a four-case smoke or an error-bucket repair into overall accuracy.")}</p></section>

<section class="section"><h2>{pair("452 条严格审计口径","Strict audit scope for 452 cases")}</h2>
<div class="metrics"><div class="metric"><b>369 / 452</b><small>81.64% · Wilson CI 77.81–84.93%</small></div><div class="metric"><b>49</b><small>{pair("仅“无需执行”回执","idempotent-only receipts")}</small></div><div class="metric"><b>427 / 23 / 2</b><small>Edge TTS / exact index / synth failures</small></div><div class="metric"><b>84.51% / 85.18%</b><small>{pair("标签敏感性上限","label-sensitivity ceilings")}</small></div></div>
<p>{pair("合法名称是“单音色 clean 合成语音下 expected-tool successful-or-idempotent receipt rate”，不是端到端任务成功率。369 条把真实成功和“已经是目标状态”的幂等回执合并；49 条仅靠无需执行，后续必须单列物理执行率。",
"The valid name is “expected-tool successful-or-idempotent receipt rate under single-voice clean synthetic speech,” not end-to-end task success. The 369 combine physical success with already-satisfied idempotent receipts; 49 are idempotent-only and physical execution must be reported separately.")}</p>
<div class="grid"><article class="card"><h3>{pair("音频可复现性","Audio reproducibility")}</h3><p>{pair("427 条运行时 Edge TTS、23 条索引精确匹配、2 条合成失败；全部单音色 clean single-turn。Git 中没有 452 WAV/LFS，也未冻结逐条 WAV hash，因此同一句重新合成不是同一输入。",
"427 used runtime Edge TTS, 23 exact index matches, and two synthesis failures; all are single-voice clean single-turn. Git has no 452 WAV/LFS and no per-WAV frozen hashes, so resynthesis is not the same input.")}</p></article>
<article class="card"><h3>{pair("标签敏感性，不是改分","Label sensitivity, not relabeling")}</h3><p>{pair("至少 13 条高置信语义等价/标签冲突对应敏感性上限 84.51%；另 3 条疑似若全部成立也仅 85.18%。典型冲突涉及音效模式、电子/流媒体后视镜、坐垫角度与座椅位置。未经双人独立裁决，不能直接改标签。",
"At least 13 high-confidence semantic-equivalence/label conflicts yield an 84.51% sensitivity ceiling; adding all three suspected cases reaches only 85.18%. Typical conflicts involve sound-effect mode, electronic/streaming rear-view mirror, and cushion angle versus seat position. Labels cannot change without two-person independent adjudication.")}</p></article>
<article class="card"><h3>CarSim / {pair("最终态缺口","final-state gap")}</h3><p>{pair("现有 CarSim 主要按 tool 而非 tool+position 保存状态；452 manifest 没有 expected_args/expected_final_state。122 复杂集的最终态由调用重放推导，不是车辆或独立模拟器真实回读。",
"Current CarSim primarily keys state by tool rather than tool+position; the 452 manifest has no expected_args/expected_final_state. Final state in the 122 complex suite is derived by replaying calls, not real vehicle or independent-simulator readback.")}</p></article></div>
<p class="sub">{pair("本页链接现有实现与说明作为证据入口，但不声称这次只读审计已经单独发布为 GitHub 文件。",
"This page links existing implementation and documentation as evidence entry points, but does not claim the read-only audit was separately published as a GitHub file.")}</p>
<div class="legend"><a class="btn" href="https://github.com/ISS-2030Lab/StreamingModelHarness/blob/automation/agent-h20-loop/evolution/h20_runner.py">h20_runner.py</a><a class="btn" href="https://github.com/ISS-2030Lab/StreamingModelHarness/blob/automation/agent-h20-loop/evolution/manifest.py">manifest.py</a><a class="btn" href="https://github.com/ISS-2030Lab/StreamingModelHarness/blob/automation/agent-h20-loop/harness_b/car_sim.py">car_sim.py</a><a class="btn" href="https://github.com/ISS-2030Lab/StreamingModelHarness/blob/automation/agent-h20-loop/docs/HYBRID_C.md">HYBRID_C.md</a></div></section>

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
<article class="card risk high"><h3>e2e {pair("口径","scope")}</h3><p>{pair("1241.6ms 是 commit→Relay 首音频，不是车控落地；call P95 为 1818.7ms。0.7s VAD 只是结果元数据，当前 runner 未真实等待，不能加减成用户端时延。","1241.6ms is commit→Relay first audio, not vehicle-control landing; call P95 is 1818.7ms. The 0.7s VAD value is result metadata only—the current runner does not actually wait it—so it cannot be added to or subtracted from user latency.")}</p></article>
<article class="card risk high"><h3>{pair("正确性代理指标","Correctness proxies")}</h3><p>{pair("工具名命中不等于参数、执行顺序或最终车态成功；4/4 与 24/31 也都不能称为 99%。","A tool-name hit is not parameter, execution-order, or final-state success. Neither 4/4 nor 24/31 may be called 99%.")}</p></article>
<article class="card risk medium"><h3>{pair("选择与归因","Selection and attribution")}</h3><p>{pair("日报到代码存在选择偏差；单变量要求与多组件组合的归因冲突，必须补消融和反事实对照。","Report-to-code selection can be biased. Single-variable requirements conflict with multi-component attribution, requiring ablations and counterfactual controls.")}</p></article>
<article class="card risk high"><h3>{pair("错误桶过拟合","Error-bucket overfit")}</h3><p>{pair("规则针对 31 条错误桶可能只记住局部模式；必须在冻结 holdout 验证。工具描述增强 0/31 是已记录负结果，不能隐藏。","Rules for a 31-case bucket may memorize local patterns and require frozen-holdout validation. Tool-description enhancement at 0/31 is a recorded negative result and must remain visible.")}</p></article>
<article class="card risk high"><h3>{pair("自动 Agent 边界","Automated-agent boundary")}</h3><p>{pair("Agent 可实现候选、登记证据和运行评测，但不得修改真值、删除难例、降低阈值或把无结果任务标成成功。","An agent may implement candidates, register evidence, and run evaluations, but may not edit truth, remove hard cases, lower thresholds, or mark a result-less task successful.")}</p></article>
</div></section>

<section class="section"><h2>{pair("必须立刻修","Must fix immediately")}</h2><div class="steps">
<article class="step"><h3>{pair("锁定架构与 provenance","Lock architecture and provenance")}</h3><p>{pair("manifest 明确 architecture/profile：B pure、B+audio-derived SoulX、C；逐条记录 candidate、ASR、SoulX 来源。默认 asr_prefetch 只能算 C 变体，禁止替代 B pure。",
"Manifest must name architecture/profile—B pure, B+audio-derived SoulX, or C—and record candidate, ASR, and SoulX provenance per row. Default asr_prefetch is a C variant and cannot replace B pure.")}</p></article>
<article class="step"><h3>{pair("冻结真实输入与判停","Freeze real inputs and endpointing")}</h3><p>{pair("版本化 452 WAV 或可验证对象存储清单及 SHA-256；真实等待并记录 VAD，加入多音色/噪声/AEC 双讲/多人/chat 安全集。",
"Version the 452 WAVs or a verifiable object-store manifest with SHA-256; actually wait and record VAD, adding multi-voice/noise/AEC double-talk/multi-speaker/chat safety sets.")}</p></article>
<article class="step"><h3>{pair("拆开执行与最终态","Separate execution and final state")}</h3><p>{pair("把无需执行从物理成功中分离；452 补 expected_args 与 tool+position expected_final_state，使用独立 CarSim/车辆回读核验，不从模型 call 自证。",
"Separate idempotent receipts from physical success; add expected_args and tool+position expected_final_state to all 452, verified by independent CarSim/vehicle readback rather than the model call proving itself.")}</p></article>
<article class="step"><h3>{pair("实现真实流式 ASR 与统计审计","Implement streaming ASR and statistical audit")}</h3><p>{pair("音频播放时增量转写和可取消 RAG，不能先完整转写；运行多 seed、报告 Wilson/分桶 CI，13+3 标签冲突由双人盲审裁决并保留原标签审计轨迹。",
"Transcribe incrementally during playback with cancellable RAG, not full transcription first; run multiple seeds, report Wilson/bucket CIs, and adjudicate 13+3 label conflicts with two-person blind review while preserving original-label audit trails.")}</p></article>
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
<div class="metric"><b>369 / 452</b><small>{pair("expected-tool 成功或幂等回执率 · 81.64%","expected-tool successful-or-idempotent receipt rate · 81.64%")}</small></div>
<div class="metric"><b>1241.6ms</b><small>e2e P95</small></div></div>
<p class="callout bad">{pair("这些数字属于 B pure-audio 组合，不属于 Hybrid C。81.64% 的严格名称是单音色 clean 合成语音下 expected-tool successful-or-idempotent receipt rate（Wilson CI 77.81–84.93%），其中 49 条仅无需执行；它不是端到端任务成功率。1241.6ms 只是 commit→Relay 首音频，call P95 为 1818.7ms。","These numbers belong to the B pure-audio combination, not Hybrid C. The precise 81.64% metric is expected-tool successful-or-idempotent receipt rate under single-voice clean synthetic speech (Wilson CI 77.81–84.93%), including 49 idempotent-only receipts; it is not end-to-end task success. 1241.6ms is commit→Relay first audio only; call P95 is 1818.7ms.")}</p>
<h3>{pair("4 条 Hybrid C 冒烟","Four-case Hybrid C smoke")}</h3><div class="metrics">
<div class="metric"><b>4 / 4</b><small>{pair("仅该冒烟集","this smoke set only")}</small></div>
<div class="metric"><b>≈1195ms</b><small>e2e</small></div>
<div class="metric"><b>≈975ms</b><small>call</small></div></div>
<p class="callout">{pair("4 条样本证明链路可工作，不证明总体准确率，也不能外推到 452 或 122 条集合。当前 ASR 预取先完整转写 WAV 再播放，只是耗时可隐藏近似，不是真流式并发。","Four cases prove the path can work; they do not establish overall accuracy and cannot be extrapolated to 452 or 122 cases. Current ASR prefetch fully transcribes the WAV before playback, approximating hidden cost rather than true streaming concurrency.")}</p>
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
