"""Render the normal Radar daily report without any Agent call."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def write_if_changed(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8", newline="\n")
    return True


def validate_packet(value: Any, target_date: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("packet must be an object")
    if value.get("schema_version") != 1 or value.get("kind") != "daily_report":
        raise ValueError("unsupported packet schema")
    if value.get("target_date") != target_date:
        raise ValueError("packet target date mismatch")
    if not isinstance(value.get("project_status"), str):
        raise ValueError("project_status must be text")
    if not isinstance(value.get("latest_items"), list):
        raise ValueError("latest_items must be a list")
    for row in value["latest_items"]:
        if not isinstance(row, dict) or not isinstance(row.get("title"), str):
            raise ValueError("latest item schema is not covered")
    return value


def compact_status(text: str, limit: int = 100) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    selected = []
    for line in lines:
        if line.startswith("生成时间："):
            continue
        selected.append(line)
        if len(selected) >= limit:
            selected.append("")
            selected.append("> 状态快照已按确定性行数上限截断；完整事实见 project_status。")
            break
    return "\n".join(selected).strip()


def item_lines(items: list[dict[str, Any]], limit: int = 10) -> list[str]:
    rows = []
    for item in items[:limit]:
        title = item["title"].replace("\n", " ").strip()
        url = str(item.get("url") or "")
        score = item.get("score")
        summary = str(item.get("summary_zh") or "").replace("\n", " ").strip()
        link = f"[{title}]({url})" if url.startswith(("http://", "https://")) else title
        rows.append(f"- {link} · score={score if score is not None else 'unknown'}"
                    + (f"：{summary}" if summary else ""))
    return rows


def render(repo: Path, packet: dict[str, Any], target_date: str) -> dict[str, Any]:
    status = compact_status(packet["project_status"])
    items = item_lines(packet["latest_items"])
    items_text = "\n".join(items) if items else "- 当日无新增结构化高价值条目。"
    detail = f"""# 全双工语音技术增量调研

更新日期：{target_date}  
生成方式：确定性事实骨架（0-Agent）  
面向项目：StreamingModelHarness

## P0 / P1 / P2 结论

- P0：保持冻结真值、安全门、单变量与同口径基线；本模板不自动提出未经核验的新实现候选。
- P1：仅将结构化条目列入待人工/后续精读队列；正文事实仍由全文精读流程核验。
- P2：若现有 schema 无法表达新证据，记录 `schema_uncovered`，不得自动升级到高价模型。

## StreamingModelHarness 当前进展与问题

{status or "项目状态快照为空；本日不生成推断。"}

## 当日结构化证据

{items_text}

## 问题、证据与实验门

| 问题 | 当前证据 | 建议动作 | 成功门槛 |
|---|---|---|---|
| 成本与上下文膨胀 | shared cost ledger / Dashboard baseline | 复用缓存、压缩 packet、限制调用日 | soft/hard 门内 |
| 新技术候选 | 仅限上方结构化公开链接 | 先全文核验，再单变量离线门 | 冻结 canary 零退化 |

## 今日建议路线

1. 优先执行确定性同步、去重、离线筛选和结果回收。
2. Harness 实现只在北京时间周一/三/五及预算允许时启动。
3. publication/patent 继续使用确定性模板，0-Agent。

## 风险提醒

- 本报告没有把摘要、标题或模型润色当作论文正文事实。
- 历史 Dashboard 混合手工聊天与自动化，不能反推 pipeline/stage。
- 手工聊天不受本地调度门控制，仍需账户级 spend limit。
"""
    brief = f"""# 每日调研日报

日期：{target_date}  
生成方式：确定性事实骨架（0-Agent）

方向：成本治理（减少调用与上下文；Radar 默认 Included Composer；Harness 仅周一/三/五实现）

方向：证据筛选（先脚本去重和结构化 packet；全文精读每天最多3篇 canonical 论文）

方向：实验闭环（非实现日正常记录 `no_agent_day` / `cost_scheduled`，继续同步和结果回收）

风险：历史 Dashboard 无 pipeline/stage，手工聊天不受本地门控制。
"""
    detail_path = repo / "reports" / f"全双工语音技术增量调研-{target_date}.md"
    brief_path = repo / "reports" / f"每日调研日报-{target_date}.md"
    changed = [
        write_if_changed(detail_path, detail),
        write_if_changed(brief_path, brief),
    ]
    candidate_path = repo / "data/handoff/candidates" / f"{target_date}.json"
    candidate_created = False
    if not candidate_path.exists():
        candidate = {
            "schema_version": 1,
            "date": target_date,
            "evidence_cutoff": f"{target_date}T10:30:00+08:00",
            "publication_safety": "public-safe; deterministic template",
            "generation": "deterministic_no_agent",
            "candidates": [],
        }
        candidate_created = write_if_changed(
            candidate_path, json.dumps(candidate, ensure_ascii=False, indent=2) + "\n")
    result_hash = hashlib.sha256(
        (detail + "\0" + brief).encode("utf-8")).hexdigest()
    return {
        "status": "complete", "schema_covered": True,
        "reports_changed": any(changed),
        "candidate_created": candidate_created,
        "result_hash": result_hash,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--target-date", required=True)
    args = parser.parse_args()
    try:
        packet = validate_packet(
            json.loads(args.packet.read_text(encoding="utf-8-sig")),
            args.target_date)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        result = render(args.repo, {
            "project_status": "",
            "latest_items": [],
        }, args.target_date)
        result.update({
            "status": "schema_uncovered",
            "error": f"{type(exc).__name__}: {exc}",
        })
        print(json.dumps(result))
        return 2
    print(json.dumps(render(args.repo, packet, args.target_date)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
