#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build static high-value Harness solution pages from the committed snapshot."""
from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote


CST = timezone(timedelta(hours=8))
SAFE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,78}[a-z0-9])?$")

NARRATIVES = {
    "grouped-mm-hopper": {
        "problem": ("大工具清单 prefill 在 MoE 上会复制权重、增加时延，甚至触发显存不足。",
                    "Large tool-list prefills can copy MoE weights, add latency, and even exhaust memory."),
        "chain": ("位于 Thinker 的 MoE 前向路径，只优化专家计算实现，不改变工具真值或回复语义。",
                  "It sits in the Thinker MoE forward path and changes expert execution, not tool truth or response semantics."),
        "how": ("在 Hopper 上选择 grouped_mm；不支持的 GPU 必须回退 hybrid/batched_mm，并把硬件与开关写入实验记录。",
                "Select grouped_mm on Hopper; unsupported GPUs must fall back to hybrid/batched_mm with hardware and switch recorded."),
    },
    "terse-execution-receipt": {
        "problem": ("成功回执过长会重复注入 KV，让每次工具闭环都付出额外 token 与尾延迟。",
                    "Verbose success receipts repeatedly enter KV, adding tokens and tail latency to every tool loop."),
        "chain": ("位于 CarSim 回执进入 Thinker 之前；只压缩成功/无需执行，失败回执保留诊断与自救。",
                  "It sits before CarSim receipts enter the Thinker; only success/idempotent receipts shrink while failures retain recovery detail."),
        "how": ("用确定性短格式表达状态，保持结构化失败 JSON；必须做开/关单变量准确率与时延回归。",
                "Use a deterministic short state format while preserving structured failure JSON; run on/off accuracy and latency ablations."),
    },
    "deterministic-post-execution-ack": {
        "problem": ("模型可能在动作失败或尚未落地时生成“已完成”，造成说做不一致。",
                    "A model may say “done” before or after a failed action, creating speech/action inconsistency."),
        "chain": ("位于真实执行回执之后、最终口播之前，只对成功或幂等回执生成确认。",
                  "It runs after the real execution receipt and before final speech, acknowledging only success or idempotence."),
        "how": ("解析受信回执；失败、未知格式和混合批次回退模型处理，下一步仍需真实最终车态回读。",
                "Parse trusted receipts; failure, unknown formats, and mixed batches fall back to the model, with real final-state readback still required."),
    },
    "relay-safe-prefix": {
        "problem": ("用户等待真实 call 时没有声音反馈，但提前承诺动作又可能产生虚假成功。",
                    "Users hear nothing while waiting for a real call, yet early action promises can falsely claim success."),
        "chain": ("位于 search 意图确认后与真实 call 前，发送可取消且不承诺结果的短前缀。",
                  "After search intent and before the real call, it sends a cancellable prefix that promises no result."),
        "how": ("前缀与 call、最终车态分别计时；首音频收益属于组合上下文，不能归因成工具成功。",
                "Time prefix, call, and final state separately; first-audio gains are combination context, not tool success."),
    },
    "audio-derived-asr-prefetch": {
        "problem": ("候选检索若等判停后才开始会增加等待，但读取 manifest 原文又是作弊。",
                    "Candidate retrieval after endpointing adds wait, while reading the manifest transcript is cheating."),
        "chain": ("从真实 WAV 派生 ASR 文本，再并行准备 RAG 候选；它属于 audio-derived C，不是 B pure。",
                  "Derive ASR text from the real WAV and prepare RAG candidates; this is audio-derived C, not B pure."),
        "how": ("保存原始/纠正 ASR、耗时和 provenance；当前冒烟先完整转写，下一门是真流式增量 ASR。",
                "Store raw/corrected ASR, latency, and provenance; current smoke fully transcribes first, so the next gate is true incremental streaming ASR."),
    },
    "voice-memory-rules": {
        "problem": ("窄域同音词和部件名会稳定误识别，但宽泛生成式纠错可能破坏原本正确文本。",
                    "Domain homophones and part names fail repeatedly, while broad generative correction can damage correct text."),
        "chain": ("位于真实 ASR 与 RAG 之间，以版本化规则做可审计、可放弃的窄域纠正。",
                  "Between real ASR and RAG, versioned rules perform auditable, abstaining domain correction."),
        "how": ("规则需保留集门控与单独消融；24/31 是与 typed resolver 共享的组合证据，不能单独归因。",
                "Rules need held-out gating and isolated ablation; 24/31 is shared with the typed resolver and cannot be attributed alone."),
    },
    "candidate-authorized-typed-resolver": {
        "problem": ("模型可能编造工具名或在近义工具中选错，直接执行会扩大权限与安全风险。",
                    "A model may invent or confuse similar tools; direct execution broadens authority and safety risk."),
        "chain": ("位于模型 action 与执行器之间，只允许最近 RAG 候选内的工具，并解析 typed 参数。",
                  "Between model action and executor, it allows only recent RAG candidates and parses typed arguments."),
        "how": ("每次修正规则带稳定 rule_id，禁止候选外扩权；仍缺完整身份、权限、幂等和最终车态合同。",
                "Each correction has a stable rule_id and cannot expand beyond candidates; identity, authorization, idempotency, and final-state contracts remain."),
    },
}


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def pair(zh: Any, en: Any) -> str:
    return f'<span class="l-zh">{esc(zh)}</span><span class="l-en">{esc(en)}</span>'


def load_snapshot(root: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(
            (Path(root) / "data" / "harness_solutions.json").read_text(
                encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {
            "schema_version": 1,
            "source": {"status": "stale", "warning": "snapshot unavailable"},
            "components": [],
            "negative_results": [],
        }


def recommended(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row for row in snapshot.get("components", [])
        if isinstance(row, dict) and row.get("recommended") is True
        and SAFE_ID.fullmatch(str(row.get("id") or ""))
    ]


def events_on(snapshot: dict[str, Any], date: str,
              *, recommended_only: bool = True) -> list[dict[str, Any]]:
    events = []
    for component in snapshot.get("components", []):
        if not isinstance(component, dict):
            continue
        if recommended_only and component.get("recommended") is not True:
            continue
        for event in component.get("history", []):
            if isinstance(event, dict) and event.get("date") == date:
                events.append({"component": component, "event": event})
    return sorted(events, key=lambda row: row["component"]["id"])


def all_dates(snapshot: dict[str, Any], today: str | None = None) -> list[str]:
    dates = {
        event.get("date")
        for component in snapshot.get("components", [])
        if isinstance(component, dict)
        for event in component.get("history", [])
        if isinstance(event, dict) and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", str(event.get("date") or ""))
    }
    dates.add(today or datetime.now(CST).date().isoformat())
    return sorted(dates, reverse=True)


def status_label(status: str) -> str:
    labels = {
        "retained": ("保留", "Retained"),
        "conditional": ("条件保留", "Conditional"),
        "partial_improvement": ("局部收益", "Partial improvement"),
        "qualified": ("已过门", "Qualified"),
        "rejected": ("未采用", "Rejected"),
        "invalid": ("无效证据", "Invalid"),
    }
    zh, en = labels.get(status, ("未知", "Unknown"))
    return f'<span class="badge solution-status {esc(status)}">{pair(zh,en)}</span>'


def scope_badge(component: dict[str, Any]) -> str:
    attribution = component.get("improvement", {}).get("attribution", "unknown")
    labels = {
        "direct": ("直接证据", "Direct evidence"),
        "component_specific": ("组件证据", "Component evidence"),
        "combined": ("组合证据", "Combined evidence"),
    }
    zh, en = labels.get(attribution, ("范围未知", "Scope unknown"))
    return f'<span class="badge">{pair(zh,en)}</span>'


def metric_value(metric: dict[str, Any]) -> str:
    value = metric.get("value")
    unit = metric.get("unit") or ""
    return f"{value if value is not None else '—'}{unit}"


def _evidence_value(field: Any, unit: str = "", *, signed: bool = False) -> str:
    value = field.get("value") if isinstance(field, dict) else None
    if value is None:
        return "unknown"
    if signed and isinstance(value, (int, float)):
        prefix = "+" if value > 0 else ""
        return f"{prefix}{value:g}{unit}"
    if isinstance(value, float):
        return f"{value:g}{unit}"
    return f"{value}{unit}"


def sample_badges(component: dict[str, Any]) -> str:
    seen, rows = set(), []
    for evidence in component.get("evidence", []):
        if not isinstance(evidence, dict):
            continue
        count = evidence.get("sample_count")
        scope = str(evidence.get("sample_scope") or "unknown")
        key = (count, scope)
        if key in seen:
            continue
        seen.add(key)
        zh = f"样本 n={count if count is not None else '未知'} · {scope}"
        en = f"Sample n={count if count is not None else 'unknown'} · {scope}"
        rows.append(f'<span class="badge evidence-scope">{pair(zh,en)}</span>')
    return "".join(rows) or f'<span class="badge">{pair("样本未知","Sample unknown")}</span>'


def comparison_line(component: dict[str, Any]) -> str:
    evidence = [
        row for row in component.get("evidence", []) if isinstance(row, dict)]
    if not evidence:
        return pair("相对基线：未知", "Versus baseline: unknown")
    if all(row.get("attribution") == "combined" for row in evidence):
        return pair(
            "相对基线：组合实验有收益，单组件提升未知",
            "Versus baseline: the combined experiment improved; "
            "the component-specific gain is unknown")
    row = next(
        (item for item in evidence if item.get("attribution") != "combined"),
        evidence[0])
    unit = str(row.get("unit") or "")
    baseline = _evidence_value(row.get("baseline"), unit)
    current = _evidence_value(row.get("current"), unit)
    delta = _evidence_value(row.get("delta"), unit, signed=True)
    metric = str(row.get("metric") or "metric")
    if baseline != "unknown" and current != "unknown":
        text = f"{metric} {baseline} → {current}（Δ {delta}）"
    elif delta != "unknown":
        text = f"{metric} Δ {delta}（基线/当前绝对值未知）"
    elif current != "unknown":
        text = f"{metric} 基线未知 → {current}（提升未知）"
    else:
        text = f"{metric}：相对基线未知"
    return pair("相对基线：" + text, "Versus baseline: " + text)


def evidence_table(component: dict[str, Any]) -> str:
    rows = []
    maturity = component.get("evidence_maturity") or "unknown"
    for row in component.get("evidence", []):
        if not isinstance(row, dict):
            continue
        unit = str(row.get("unit") or "")
        attribution = str(row.get("attribution") or "unknown")
        experiment = row.get("evidence", {})
        ab = row.get("independent_ab")
        ab_text = "yes" if ab is True else "no" if ab is False else "unknown"
        attribution_text = (
            pair("组合实验有收益，单组件提升未知",
                 "Combined experiment improved; component-specific gain unknown")
            if attribution == "combined" else esc(attribution))
        rows.append(
            "<tr>"
            f"<td>{esc(row.get('metric') or 'unknown')}</td>"
            f"<td>{esc(_evidence_value(row.get('baseline'), unit))}</td>"
            f"<td>{esc(_evidence_value(row.get('current'), unit))}</td>"
            f"<td>{esc(_evidence_value(row.get('delta'), unit, signed=True))}</td>"
            f"<td>{esc(row.get('metric_definition') or 'unknown')}<br>"
            f"<small>{esc(row.get('direction') or 'unknown')}</small></td>"
            f"<td>n={esc(row.get('sample_count') if row.get('sample_count') is not None else 'unknown')}"
            f"<br><small>{esc(row.get('sample_scope') or 'unknown')} · "
            f"{esc(row.get('hardware') or 'unknown')}</small></td>"
            f"<td>{attribution_text}<br><small>A/B={esc(ab_text)}</small></td>"
            f"<td>{esc(experiment.get('experiment') if isinstance(experiment,dict) else 'unknown')}"
            f"<br><small>{esc(experiment.get('branch') if isinstance(experiment,dict) else 'unknown')}</small></td>"
            f"<td>{esc(row.get('confidence') or 'unknown')} / {esc(maturity)}</td>"
            "</tr>")
    if not rows:
        rows.append(
            f'<tr><td colspan="9">{pair("证据未知","Evidence unknown")}</td></tr>')
    headers = (
        ("指标", "Metric"), ("基线", "Baseline"), ("当前", "Current"),
        ("delta", "Delta"), ("定义/方向", "Definition/direction"),
        ("样本/硬件", "Sample/hardware"),
        ("归因/是否独立A/B", "Attribution/independent A/B"),
        ("实验/分支", "Experiment/branch"), ("置信/成熟度", "Confidence/maturity"),
    )
    return (
        '<div class="evidence-table-wrap"><table class="evidence-table"><thead><tr>'
        + "".join(f"<th>{pair(zh,en)}</th>" for zh, en in headers)
        + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")


def metrics(component: dict[str, Any], detailed: bool = False) -> str:
    rows = []
    for metric in component.get("improvement", {}).get("metrics", []):
        if not isinstance(metric, dict):
            continue
        shared = metric.get("attribution") == "combination_only"
        label = pair("组合上下文，不能归因", "Combination context; not attributable") if shared else pair(
            "组件指标", "Component metric")
        rows.append(
            '<div class="solution-metric">'
            f'<div><b>{esc(metric.get("name") or "unknown")}</b> '
            f'<span>{esc(metric_value(metric))}</span></div>'
            f'<div class="metric-strip {"shared" if shared else "positive"}" '
            f'aria-label="{esc(metric.get("direction") or "unknown")}"></div>'
            f'<small>{label} · {pair("样本","scope")}: '
            f'{esc(metric.get("sample_scope") or "unknown")} · n='
            f'{esc(metric.get("sample_count") if metric.get("sample_count") is not None else "unknown")}'
            "</small></div>")
    if not rows:
        return f'<p class="no-updates">{pair("指标未知","Metrics unknown")}</p>'
    return "".join(rows if detailed else rows[:2])


def _list(values: Any) -> str:
    rows = values if isinstance(values, list) else []
    if not rows:
        return f"<p>{pair('未知','Unknown')}</p>"
    return "<ul>" + "".join(
        f"<li>{pair(value,'Source record: ' + str(value))}</li>"
        for value in rows) + "</ul>"


def _source_link(value: str, snapshot: dict[str, Any]) -> str:
    if "arXiv:" in value or "arxiv:" in value:
        match = re.search(r"(\d{4}\.\d{4,5})", value)
        if match:
            return f"https://arxiv.org/abs/{match.group(1)}"
    if value.startswith("http://") or value.startswith("https://"):
        return value
    path = re.split(r"[:#]L?\d|#\d", value, maxsplit=1)[0]
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", path) or ".." in Path(path).parts:
        return ""
    source = snapshot.get("source", {})
    repository, branch = source.get("repository", ""), source.get("branch", "")
    if not repository.startswith("https://github.com/") or not re.fullmatch(
            r"[A-Za-z0-9._/-]+", str(branch)):
        return ""
    safe_path = "/".join(quote(part, safe="") for part in path.split("/"))
    return f"{repository}/blob/{branch}/{safe_path}"


def source_links(component: dict[str, Any], snapshot: dict[str, Any]) -> str:
    rows = []
    for value in component.get("sources", []):
        url = _source_link(str(value), snapshot)
        text = pair(value, value)
        rows.append(
            f'<li><a href="{esc(url)}" rel="noopener noreferrer">{text}</a></li>'
            if url else f"<li>{text}</li>")
    return "<ul>" + "".join(rows) + "</ul>" if rows else pair("未知", "Unknown")


def component_card(component: dict[str, Any], base: str, event: dict[str, Any] | None = None) -> str:
    component_id = esc(component["id"])
    event_label = ""
    if event:
        event_label = status_label(str(component.get("status") or "")) + " " + pair(
            "新增" if event.get("kind") == "added" else "更新",
            "Added" if event.get("kind") == "added" else "Updated")
    status = str(component.get("status") or "")
    reason_label = (
        pair("条件保留原因", "Conditional retention reason")
        if status == "conditional" else
        pair("拒绝原因", "Rejection reason") if status in {"rejected", "invalid"}
        else pair("保留原因", "Retention reason"))
    reason = component.get("conditional_reason") or component.get("retention_reason") or "未知"
    return (
        f'<article class="card solution-card" id="solution-{component_id}">'
        f'<div class="meta">{event_label or status_label(str(component.get("status") or ""))}'
        f'{scope_badge(component)}</div>'
        f'<div class="t"><a href="{base}/solutions/{component_id}.html">'
        f'{esc(component.get("name") or component_id)}</a></div>'
        f'<p><b>{reason_label}:</b> {pair(reason, "Source rationale: " + str(reason))}</p>'
        f'<p class="solution-comparison"><b>{comparison_line(component)}</b></p>'
        f'<div class="meta">{sample_badges(component)}</div>'
        f'{metrics(component)}</article>')


def stale_banner(snapshot: dict[str, Any]) -> str:
    source = snapshot.get("source", {})
    if source.get("status") == "fresh":
        return (
            '<p class="solution-source ok">'
            + pair("Harness 数据源已同步", "Harness source synchronized")
            + f' · <code>{esc(str(source.get("commit") or "")[:12])}</code></p>')
    return (
        '<p class="solution-source stale"><b>'
        + pair("数据源告警：使用上次快照", "Source warning: using previous snapshot")
        + "</b> · " + pair(
            source.get("warning") or "同步源不可用",
            "Harness source unavailable; existing data was preserved") + "</p>")


def feedback_section(snapshot: dict[str, Any], date: str, base: str) -> str:
    events = events_on(snapshot, date)
    body = "".join(
        component_card(row["component"], base, row["event"]) for row in events)
    if not body:
        body = (
            '<p class="no-updates">'
            + pair("当日新增/更新的保留组件：0。", "Retained components added/updated today: 0.")
            + "</p>")
    return (
        '<section class="solution-feedback"><h2>'
        + pair("实验反馈 / 保留组件", "Experiment feedback / retained components")
        + f' · {esc(date)}</h2>{body}<p><a class="btn" href="{base}/solutions/{esc(date)}.html">'
        + pair("查看当日方案页", "Open daily solutions") + "</a></p></section>")


def detail_page(component: dict[str, Any], snapshot: dict[str, Any], base: str) -> str:
    component_id = component["id"]
    narrative = NARRATIVES.get(component_id, {
        "problem": ("来源未提供通俗问题描述。", "No plain-language problem statement was supplied."),
        "chain": ("链路位置未知。", "Pipeline position unknown."),
        "how": ("实现细节未知。", "Implementation details unknown."),
    })
    runtime = component.get("runtime", {})
    experiment_rows = component.get("experiment_records", [])
    experiments = []
    for row in experiment_rows:
        link = row.get("github_url")
        title = esc(row.get("id") or "unknown")
        experiments.append(
            f'<li>{f"<a href={json.dumps(link)}>{title}</a>" if link else title}'
            f' · {status_label(str(row.get("status") or ""))}'
            f' · baseline={esc(row.get("baseline_id") or "unknown")}'
            f' · n={esc(row.get("sample_count") if row.get("sample_count") is not None else "unknown")}'
            f'<details><summary tabindex="0">{pair("实验字段","Experiment fields")}</summary>'
            f'<p><b>delta:</b> <code>{esc(json.dumps(row.get("delta"), ensure_ascii=False))}</code></p>'
            f'<p><b>safety:</b> <code>{esc(json.dumps(row.get("safety"), ensure_ascii=False))}</code></p>'
            f'<p><b>{pair("未改善/局限","Not improved / limits")}:</b> '
            f'{pair(row.get("known_limitations") or "未知", "Source-record limitation: " + str(row.get("known_limitations") or "Unknown"))}</p>'
            f'<p><b>{pair("复现","Reproduce")}:</b> <code>{esc(row.get("reproduce") or "unknown")}</code></p>'
            "</details></li>")
    files = runtime.get("files", []) if isinstance(runtime, dict) else []
    file_rows = []
    for row in files:
        path, url = row.get("path", ""), row.get("github_url", "")
        file_rows.append(
            f'<li><a href="{esc(url)}" rel="noopener noreferrer">{esc(path)}</a></li>'
            if url else f"<li>{esc(path or 'unknown')}</li>")
    history = component.get("history", [])
    return f"""<div class="item-page solution-detail">
<p><a class="btn" href="{base}/solutions/">{pair("← 高收益组件","← High-value solutions")}</a></p>
<h2>{esc(component.get("name") or component_id)}</h2>
<div class="meta">{status_label(str(component.get("status") or ""))}{scope_badge(component)}
<span class="badge">{pair("证据成熟度","Evidence maturity")}: {esc(component.get("status") or "unknown")}</span></div>
<p><b>{pair(
    "拒绝原因" if component.get("status") in {"rejected","invalid"} else
    "条件保留原因" if component.get("status") == "conditional" else "保留原因",
    "Rejection reason" if component.get("status") in {"rejected","invalid"} else
    "Conditional retention reason" if component.get("status") == "conditional" else
    "Retention reason"
)}:</b> {pair(
    component.get("conditional_reason") or component.get("retention_reason") or "未知",
    "Source rationale: " + str(component.get("conditional_reason") or
                                component.get("retention_reason") or "Unknown")
)}</p>
<p class="solution-comparison"><b>{comparison_line(component)}</b></p>
<section class="solution-flow" aria-label="Solution pipeline position">
<span>{pair("论文 / 日报","Paper / report")}</span><b>→</b>
<span>{pair("组件","Component")}</span><b>→</b>
<span>{pair("实验","Experiment")}</span><b>→</b>
<span>{pair("下一验证门","Next gate")}</span></section>
<section><h3>{pair("它解决什么","What it solves")}</h3><p>{pair(*narrative["problem"])}</p></section>
<section><h3>{pair("改了哪段链路","Pipeline change")}</h3><p>{pair(*narrative["chain"])}</p></section>
<section><h3>{pair("怎么实现","Implementation")}</h3><p>{pair(*narrative["how"])}</p>
<p><b>{pair("开关","Switch")}:</b> <code>{esc(runtime.get("switch") if isinstance(runtime,dict) else "unknown")}</code></p>
<ul>{"".join(file_rows) if file_rows else f"<li>{pair('文件未知','Files unknown')}</li>"}</ul></section>
<section><h3>{pair("指标、delta 与样本范围","Metrics, delta, and scope")}</h3>{metrics(component, detailed=True)}
<p class="note">{pair("shared / combined 指标只作为整套方案上下文，不归因到本组件。",
"Shared/combined metrics are whole-candidate context and are not attributed to this component.")}</p></section>
<section><h3>{pair("证据表","Evidence table")}</h3>{evidence_table(component)}</section>
<section><h3>{pair("所属实验、基线与分支","Experiments, baselines, and branches")}</h3>
<ul>{"".join(experiments) if experiments else f"<li>{pair('未知','Unknown')}</li>"}</ul></section>
<section><h3>{pair("风险、兼容性与未改善项","Risks, compatibility, and non-gains")}</h3>
<p><b>{pair("兼容性","Compatibility")}:</b> {pair(component.get("compatibility") or "未知","Source compatibility record: " + str(component.get("compatibility") or "Unknown"))}</p>
{_list(component.get("risks"))}</section>
<section><h3>{pair("如何复核来源","Source evidence")}</h3>{source_links(component,snapshot)}</section>
<section><h3>{pair("下一验证门","Next validation gate")}</h3>
<p><b>{pair("为什么是当前状态","Why this status")}:</b>
{pair(component.get("conditional_reason") or component.get("retention_reason") or "未知",
"Source status rationale: " + str(component.get("conditional_reason") or component.get("retention_reason") or "Unknown"))}</p>
<p><b>{pair("升级为 retained 需要","Required to become retained")}:</b>
{pair(component.get("next_validation_gate") or "未知","Source next-gate record: " + str(component.get("next_validation_gate") or "Unknown"))}</p></section>
<details><summary tabindex="0">{pair("版本与变更历史","Version and change history")}</summary>{_list([
    f"{row.get('date','unknown')} · {row.get('kind','unknown')} · {row.get('summary','')}"
    for row in history if isinstance(row,dict)])}</details>
</div>"""


def build(root: str | Path, docs: str | Path, base: str,
          shell: Callable[[str, str, str], str]) -> dict[str, Any]:
    root, docs = Path(root), Path(docs)
    snapshot = load_snapshot(root)
    target = docs / "solutions"
    target.mkdir(parents=True, exist_ok=True)
    expected = {"index.html"}
    good = recommended(snapshot)
    negatives = [
        row for row in snapshot.get("negative_results", [])
        if isinstance(row, dict) and row.get("status") in {"rejected", "invalid"}
    ]
    rejected_components = [
        row for row in snapshot.get("components", [])
        if isinstance(row, dict) and row.get("status") in {"rejected", "invalid"}
        and SAFE_ID.fullmatch(str(row.get("id") or ""))
    ]
    cards = "".join(component_card(row, base) for row in good)
    negative_cards = "".join(
        component_card(row, base) for row in rejected_components)
    if not negative_cards:
        negative_cards = "".join(
            f'<article class="card"><div class="meta">{status_label(str(row.get("status") or ""))}</div>'
            f'<div class="t">{esc(row.get("single_variable") or row.get("id") or "unknown")}</div>'
            f'<p>{pair(row.get("conclusion") or "未知",row.get("conclusion") or "Unknown")}</p></article>'
            for row in negatives)
    today = datetime.now(CST).date().isoformat()
    index_body = (
        f'<h2 class="day">{pair("高收益组件","High-value components")} · {len(good)}</h2>'
        + stale_banner(snapshot)
        + f'<p><a class="btn" href="{base}/solutions/{today}.html">'
        + pair("今日新增 / 更新", "Added / updated today")
        + f' · {len(events_on(snapshot,today))}</a></p>'
        + (cards or f'<p class="no-updates">{pair("暂无符合严格门槛的组件","No components meet the strict gate")}</p>')
        + f'<h2 class="day">{pair("负结果 / 未采用","Negative results / not adopted")}</h2>'
        + (negative_cards or f'<p class="no-updates">{pair("暂无记录","No records")}</p>'))
    (target / "index.html").write_text(
        shell("Solutions · cockpit-agent-radar", index_body, "solutions"),
        encoding="utf-8")
    for component in good + rejected_components:
        name = component["id"] + ".html"
        expected.add(name)
        (target / name).write_text(shell(
            f"{component.get('name')} · Solutions",
            stale_banner(snapshot) + detail_page(component, snapshot, base),
            "solutions"), encoding="utf-8")
    dates = set(all_dates(snapshot, today))
    report_dir = root / "reports"
    if report_dir.is_dir():
        for path in report_dir.glob("*.md"):
            match = re.search(r"(\d{4}-\d{2}-\d{2})$", path.stem)
            if match:
                dates.add(match.group(1))
    dates = sorted(dates, reverse=True)
    for date in dates:
        name = date + ".html"
        expected.add(name)
        events = events_on(snapshot, date)
        body = (
            f'<h2 class="day">{pair("每日方案变化","Daily solution changes")} · '
            f'{esc(date)} · {len(events)}</h2>{stale_banner(snapshot)}'
            + ("".join(component_card(
                row["component"], base, row["event"]) for row in events)
               or f'<p class="no-updates">{pair("当日新增/更新：0","Added/updated that day: 0")}</p>')
            + f'<p><a class="btn" href="{base}/solutions/">{pair("← 全部组件","← All solutions")}</a></p>')
        (target / name).write_text(
            shell(f"{date} · Solutions", body, "solutions"), encoding="utf-8")
    for path in target.glob("*.html"):
        if path.name not in expected:
            path.unlink()
    return {
        "recommended": len(good),
        "negative": len(negatives),
        "today": len(events_on(snapshot, today)),
        "pages": len(expected),
        "status": snapshot.get("source", {}).get("status", "stale"),
    }
