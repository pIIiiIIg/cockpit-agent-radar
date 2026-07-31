#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""零 API 的论文摘要速读回填。

目标不是冒充全文解读，而是让新论文抓取后立即有结构化入口；Cursor 定时 Agent
随后把 review_status=abstract_backfill 的条目升级为基于正文的深度讲解。
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ITEMS = os.path.join(ROOT, "data", "items.json")
EXPLANATIONS = os.path.join(ROOT, "data", "explanations.json")
CST = timezone(timedelta(hours=8))


def sentences(text):
    return [part.strip() for part in re.split(r"(?<=[。！？])", text or "")
            if part.strip()]


def generic_problem(title):
    low = title.lower()
    if any(word in low for word in ("echo", "noise suppression", "acoustic")):
        return "助手播报产生的回声、车内噪声和硬件时延会重新进入麦克风，破坏双讲检测、语音理解和用户打断。"
    if any(word in low for word in ("benchmark", "evaluation", "assessment", "survey")):
        return "现有全双工或多模态系统缺少统一、可复现的评测方法，导致不同架构和交互失败难以横向比较。"
    if any(word in low for word in ("vad", "turn", "interrupt", "interaction")):
        return "传统能量 VAD 和轮次式流水线难以区分停顿、附和、真正插话和语义结束，容易造成抢话或漏响应。"
    if any(word in low for word in ("motion", "facial", "avatar", "video")):
        return "仅处理语音的助手无法覆盖面对面交互中的动作、表情或连续视觉线索，跨模态时序也难以保持同步。"
    if any(word in low for word in ("cache", "prune", "efficient", "serving", "latency")):
        return "实时多模态推理同时受到延迟、KV cache 增长和计算资源约束，需要在质量与持续流式处理之间取舍。"
    if any(word in low for word in ("reason", "thinking", "reinforcement", "alignment")):
        return "全双工模型在追求低延迟交互时容易牺牲推理、指令遵循或长期状态一致性。"
    return "论文针对全双工语音或流式多模态交互中的一项具体能力缺口提出新方法。"


def fallback(item):
    zh_parts = sentences(item.get("summary_zh"))
    zh = (item.get("summary_zh") or item.get("summary_en") or "").strip()
    tl_dr = zh_parts[0] if zh_parts else zh[:240]
    fit = zh_parts[1:] if len(zh_parts) > 1 else []
    if not fit:
        fit = ["需要结合 StreamingModelHarness 当前输入流式、判停后生成、晚注入工具和外挂 TTS 的架构进一步评估。"]
    return {
        "tl_dr": tl_dr[:500],
        "problem": generic_problem(item.get("title", "")),
        "method": zh[:1800],
        "workflow": [],
        "findings": [],
        "project_fit": fit[:4],
        "limitations": [
            "当前为基于公开摘要的速读，尚未逐项核验正文实验、实现细节和开放状态；Cursor 讲解 Agent 会继续升级。"
        ],
        "open_source": {
            "status": "unknown",
            "code_url": "",
            "model_url": "",
            "note": "摘要未提供足够证据，等待正文与官方项目页核验。"
        },
        "source_depth": "abstract",
        "generated_at": datetime.now(CST).isoformat(),
        "generated_by": "deterministic abstract backfill",
        "review_status": "abstract_backfill"
    }


def main():
    refresh = "--refresh" in sys.argv
    with open(ITEMS, encoding="utf-8") as stream:
        items = json.load(stream)["items"]
    try:
        with open(EXPLANATIONS, encoding="utf-8") as stream:
            explanations = json.load(stream)
    except Exception:
        explanations = {}
    added = updated = 0
    for item in items:
        if item.get("kind") != "paper":
            continue
        old = explanations.get(item["id"])
        if old and not (refresh and old.get("review_status") == "abstract_backfill"):
            continue
        explanations[item["id"]] = fallback(item)
        if old:
            updated += 1
        else:
            added += 1
    if added or updated:
        tmp = EXPLANATIONS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as stream:
            json.dump(explanations, stream, ensure_ascii=False, indent=1)
            stream.write("\n")
        os.replace(tmp, EXPLANATIONS)
    print(f"abstract explanations: added {added}, updated {updated}, "
          f"total {len(explanations)}")


if __name__ == "__main__":
    main()
