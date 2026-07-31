#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""增强通道·云端版：调 Kimi 为新条目补中文摘要和论文结构化讲解。

在 GitHub Actions 里跑（key 走 MOONSHOT_API_KEY secret），本地调试可用
MOONSHOT_KEY_FILE 指到 key 文件。设计要求与定时层同款：
- 零第三方依赖
- **优雅缺席**：没 key / API 挂了 / 返回不合法 → 打日志退出 0，绝不拖垮建站
- 绝不打印 key；摘要写回 items.json，论文讲解独立写 explanations.json
- 深度讲解只使用论文正文/摘要作为事实依据；对项目的建议明确标为编辑判断
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from paper_context import paper_context

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "items.json")
EXPLANATIONS = os.path.join(ROOT, "data", "explanations.json")
BASE = os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
MODEL = os.environ.get("MOONSHOT_MODEL", "kimi-k3")
BATCH = 8          # 每次请求塞几条（省往返；太多会让 JSON 输出不稳）
MAX_ITEMS = 20     # 单次运行上限
MAX_EXPLANATIONS = 6  # 全文讲解较长；每天三班可持续回填历史论文


def get_key():
    k = os.environ.get("MOONSHOT_API_KEY", "").strip()
    if k:
        return k
    f = os.environ.get("MOONSHOT_KEY_FILE", "").strip()
    if f and os.path.isfile(f):
        return open(f, encoding="utf-8").read().strip()
    return ""


SYS = """你是"cockpit-agent-radar"技术雷达站的编辑。这个站服务于一个具体项目：
把视觉+音频+文本多模态模型(如 Qwen3-Omni)通过自研 harness 做成全双工的座舱
语音视觉助手（流式进 KV、边说边听、晚注入工具清单、外挂 TTS）。

给你若干条目(论文/仓库/新闻/模型)，为每条写 summary_zh：
- 2~3 句中文。第一句说它是什么；第二句说它与全双工/流式/多模态/座舱语音
  助手的关系(能借鉴什么、解决什么痛点)；确实不相关就直说"与本站主题相关性
  有限，胜在……"。
- 不是翻译。不编造原文没有的信息，信息不足就基于给出的摘要保守概括。
- 只输出 JSON 数组，格式 [{"id":"...","summary_zh":"..."}]，不要任何其他文字。"""

EXPLAIN_SYS = """你是 cockpit-agent-radar 的论文解读编辑。读者正在做：
Qwen3-Omni 音频流式进 KV、判停后晚注入车控工具、Thinker 文本接外挂 TTS 的
StreamingModelHarness，目标是视觉+音频+文本的智能座舱助手。

你会收到一篇论文的标题、摘要、可能截取的公开正文以及正文中实际出现的项目链接。
请生成中文结构化讲解，严格遵守：
1. 论文事实只能来自输入材料。没有报告的指标、代码、权重和许可证必须写“不确定”。
2. “对项目的帮助”是编辑判断，不得伪装成论文结论。
3. 用普通工程师能理解的语言解释，不堆术语；方法步骤用 2~6 个短句。
4. findings 只放论文明确报告的结果；材料不足就返回空数组。
5. open_source.status 只能是 open / partial / unavailable / unknown。
   只有输入 links 中真实出现的 URL 才能写入 code_url/model_url，否则留空。
6. 只输出一个 JSON 对象，不要 Markdown 围栏或其他文字：
{
  "tl_dr":"一句话说明它是什么",
  "problem":"它解决的具体问题",
  "method":"核心思路",
  "workflow":["步骤1","步骤2"],
  "findings":["明确结果"],
  "project_fit":["对 StreamingModelHarness 的可执行启示"],
  "limitations":["论文或迁移边界"],
  "open_source":{"status":"unknown","code_url":"","model_url":"","note":"依据说明"}
}"""


def call_kimi(key, batch):
    # 不传 temperature：kimi-k3 这类推理模型只接受 1，传 0.3 直接 400
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYS},
            {"role": "user", "content": json.dumps(
                [{"id": it["id"], "kind": it["kind"], "title": it["title"],
                  "summary_en": it["summary_en"], "tags": it["tags"]}
                 for it in batch], ensure_ascii=False)}]}
    req = urllib.request.Request(
        BASE.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key})
    # 免费档限流很紧(低 RPM)：429 退避重试而不是直接放弃
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                body = json.loads(r.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 4:
                wait = 25 * (attempt + 1)
                print(f"  429 限流，等 {wait}s 重试")
                time.sleep(wait)
            else:
                raise
    text = body["choices"][0]["message"]["content"]
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    return json.loads(text)


def _clean_text(value, limit):
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def _clean_list(value, limit=6, item_limit=420):
    if not isinstance(value, list):
        return []
    return [_clean_text(row, item_limit) for row in value
            if isinstance(row, str) and _clean_text(row, item_limit)][:limit]


def normalize_explanation(raw, context):
    """白名单化模型输出，避免任意字段/链接进入站点数据。"""
    if not isinstance(raw, dict):
        raise ValueError("讲解不是 JSON object")
    required = ("tl_dr", "problem", "method")
    if any(len(_clean_text(raw.get(key), 1200)) < 8 for key in required):
        raise ValueError("讲解核心字段缺失")

    supplied = {url.rstrip("/"): url for url in context.get("links", [])}
    opened = raw.get("open_source")
    opened = opened if isinstance(opened, dict) else {}
    status = opened.get("status") if opened.get("status") in {
        "open", "partial", "unavailable", "unknown"
    } else "unknown"

    def trusted_url(value):
        return supplied.get((value or "").strip().rstrip("/"), "")

    return {
        "tl_dr": _clean_text(raw.get("tl_dr"), 500),
        "problem": _clean_text(raw.get("problem"), 1600),
        "method": _clean_text(raw.get("method"), 2000),
        "workflow": _clean_list(raw.get("workflow")),
        "findings": _clean_list(raw.get("findings")),
        "project_fit": _clean_list(raw.get("project_fit")),
        "limitations": _clean_list(raw.get("limitations")),
        "open_source": {
            "status": status,
            "code_url": trusted_url(opened.get("code_url")),
            "model_url": trusted_url(opened.get("model_url")),
            "note": _clean_text(opened.get("note"), 600),
        },
        "source_depth": context.get("depth", "abstract"),
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "generated_by": MODEL,
        "review_status": "auto",
    }


def call_kimi_explanation(key, item, context):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": EXPLAIN_SYS},
            {"role": "user", "content": json.dumps({
                "id": item["id"],
                "title": item["title"],
                "abstract": item.get("summary_en", ""),
                "source_depth": context["depth"],
                "source_text": context["text"],
                "links": context["links"],
            }, ensure_ascii=False)},
        ],
    }
    req = urllib.request.Request(
        BASE.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=240) as response:
                body = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 4:
                wait = 25 * (attempt + 1)
                print(f"  讲解 429 限流，等 {wait}s 重试")
                time.sleep(wait)
            else:
                raise
    text = body["choices"][0]["message"]["content"]
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    return normalize_explanation(json.loads(text), context)


def load_explanations():
    try:
        data = json.load(open(EXPLANATIONS, encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=1)
        stream.write("\n")
    os.replace(tmp, path)


def main():
    key = get_key()
    if not key:
        print("enhance: 无 key，跳过摘要和论文讲解——站点照常构建")
        return 0
    payload = json.load(open(DATA, encoding="utf-8"))
    rows = payload["items"]
    by_id = {it["id"]: it for it in rows}
    explanations = load_explanations()
    cutoff = (datetime.now(timezone(timedelta(hours=8)))
              - timedelta(days=3)).isoformat()
    todo = sorted([it for it in rows
                   if not it.get("summary_zh") and it["found"] >= cutoff],
                  key=lambda x: -x["score"])[:MAX_ITEMS]

    summary_done = summary_fail = 0
    for i in range(0, len(todo), BATCH):
        if i:
            time.sleep(8)          # 批间留隙，别顶着 RPM 上限打
        batch = todo[i:i + BATCH]
        try:
            for row in call_kimi(key, batch):
                it = by_id.get(row.get("id"))
                zh = (row.get("summary_zh") or "").strip()
                if it and zh and len(zh) > 15:
                    it["summary_zh"] = zh[:400]
                    summary_done += 1
        except Exception as e:
            summary_fail += 1
            print(f"enhance: 批次失败 {type(e).__name__}: {str(e)[:120]}")

    if summary_done:
        save_json(DATA, payload)

    # 新论文优先，同时按分数持续回填历史库存；每次限量，避免长正文请求顶爆限额。
    explain_todo = [it for it in rows
                    if it.get("kind") == "paper" and it["id"] not in explanations]
    explain_todo.sort(
        key=lambda it: (it.get("found", "") >= cutoff,
                        it.get("score", 0), it.get("found", "")),
        reverse=True)
    explain_todo = explain_todo[:MAX_EXPLANATIONS]
    explain_done = explain_fail = 0
    for index, item in enumerate(explain_todo):
        if index:
            time.sleep(8)
        try:
            print(f"enhance: 讲解 {item['id']} {item['title'][:54]}")
            context = paper_context(item)
            explanations[item["id"]] = call_kimi_explanation(key, item, context)
            save_json(EXPLANATIONS, explanations)
            explain_done += 1
        except Exception as exc:
            explain_fail += 1
            print(f"enhance: 讲解失败 {item['id']} "
                  f"{type(exc).__name__}: {str(exc)[:120]}")

    print(f"enhance: 中文摘要 {summary_done} 条/失败批次 {summary_fail}；"
          f"论文讲解 {explain_done} 篇/失败 {explain_fail}（model={MODEL}）")
    return 0   # 永远 0：增强层缺席不能挡定时层


if __name__ == "__main__":
    sys.exit(main())
