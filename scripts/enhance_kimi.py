#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""增强通道·云端版：调 Kimi (kimi-k3) 为新条目补中文摘要。

在 GitHub Actions 里跑（key 走 MOONSHOT_API_KEY secret），本地调试可用
MOONSHOT_KEY_FILE 指到 key 文件。设计要求与定时层同款：
- 零第三方依赖
- **优雅缺席**：没 key / API 挂了 / 返回不合法 → 打日志退出 0，绝不拖垮建站
- 绝不打印 key；绝不改 summary_zh 以外的字段（demo 生成仍归本机 Claude 通道，
  单发 API 造不出可靠的交互页，宁缺毋滥）
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "items.json")
BASE = os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
MODEL = os.environ.get("MOONSHOT_MODEL", "kimi-k3")
BATCH = 8          # 每次请求塞几条（省往返；太多会让 JSON 输出不稳）
MAX_ITEMS = 20     # 单次运行上限


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


def main():
    key = get_key()
    if not key:
        print("enhance: 无 key（MOONSHOT_API_KEY 未配置），跳过——站点照常构建")
        return 0
    items = json.load(open(DATA, encoding="utf-8"))
    by_id = {it["id"]: it for it in items["items"]}
    cutoff = (datetime.now(timezone(timedelta(hours=8)))
              - timedelta(days=3)).isoformat()
    todo = sorted([it for it in items["items"]
                   if not it.get("summary_zh") and it["found"] >= cutoff],
                  key=lambda x: -x["score"])[:MAX_ITEMS]
    if not todo:
        print("enhance: 没有待补条目")
        return 0

    done = fail = 0
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
                    done += 1
        except Exception as e:
            fail += 1
            print(f"enhance: 批次失败 {type(e).__name__}: {str(e)[:120]}")

    if done:
        json.dump(items, open(DATA, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print(f"enhance: 补中文摘要 {done} 条，失败批次 {fail}（model={MODEL}）")
    return 0   # 永远 0：增强层缺席不能挡定时层


if __name__ == "__main__":
    sys.exit(main())
