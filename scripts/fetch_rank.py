#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cockpit-agent-radar 抓取 + 相关度打分 + 合并入库。

设计约束：
- 零第三方依赖（urllib + ElementTree），Python 3.8+ 皆可跑
- 四个源各自 try/except：单源挂掉不影响其余（RSS 雷达最忌一源拖死全站）
- 代理走环境变量：笔记本上有只放海外的代理正好全用上；GitHub Actions 无代理直连
- 打分是纯关键词启发式——语义级摘要/翻译交给增强通道（RADAR_AGENT.md），
  这样定时更新永远不依赖任何 LLM key
"""
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "items.json")
CST = timezone(timedelta(hours=8))
NOW = datetime.now(CST)
UA = {"User-Agent": "cockpit-agent-radar/1.0 (+github.com/pIIiiIIg/cockpit-agent-radar)"}

# ---------------------------------------------------------------------------
# 关键词分层：权重 3 = 项目核心（全双工/流式语音/座舱），2 = 强相关，1 = 泛背景。
# 命中标题算 2 倍。短英文词用 \b 词边界防误伤（insomnia 里含 omni 这种）。
# ---------------------------------------------------------------------------
KW = {
    3: ["full-duplex", "full duplex", "speech-to-speech", "speech to speech",
        "voice-to-voice", "duplex", "omni", "realtime voice", "real-time voice",
        "streaming asr", "streaming tts", "streaming speech", "audio-visual llm",
        "speech llm", "spoken dialogue", "voice agent", "turn-taking", "barge-in",
        "realtime multimodal", "real-time multimodal", "native audio",
        "multimodal agent", "omnimodal agent", "audio-visual agent",
        "cockpit", "in-car", "全双工", "座舱", "车机", "语音助手",
        "多模态智能体", "多模态 agent"],
    2: ["multimodal", "omnimodal", "audio llm", "speech model", "voice assistant",
        "speech recognition", "speech synthesis", "text-to-speech", "kv cache",
        "streaming inference", "agent harness", "computer use", "realtime api",
        "vision-language-action", "vision language action", "video agent",
        "audio visual", "multimodal assistant", "vad", "wake word", "low latency",
        "端到端语音", "多模态"],
    1: ["agent", "asr", "tts", "llm", "voice", "audio", "assistant",
        "automotive", "driving"],
}

_SHORT = re.compile(r"^[\x00-\x7f]{1,7}$")


def _hit(kw: str, text: str) -> bool:
    if _SHORT.match(kw):
        return re.search(r"\b" + re.escape(kw) + r"\b", text) is not None
    return kw in text


def score(title: str, body: str):
    t, b = (title or "").lower(), (body or "").lower()
    s, tags = 0, []
    for w, kws in KW.items():
        for kw in kws:
            in_t, in_b = _hit(kw, t), _hit(kw, b)
            if in_t or in_b:
                s += w * (2 if in_t else 1)
                if w >= 2:
                    tags.append(kw)
    return s, tags[:6]


def http_get(url: str, headers=None, timeout=40) -> bytes:
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def http_json(url: str, headers=None, timeout=40):
    return json.loads(http_get(url, headers, timeout).decode("utf-8"))


def norm_url(u: str) -> str:
    return (u or "").strip().rstrip("/").replace("http://", "https://")


def iid(u: str) -> str:
    return hashlib.md5(norm_url(u).encode()).hexdigest()[:10]


def mk(kind, source, title, url, published, body, stars=None, bonus=0):
    s, tags = score(title, body)
    return {"id": iid(url), "kind": kind, "source": source,
            "title": re.sub(r"\s+", " ", title or "").strip(),
            "url": norm_url(url), "published": (published or "")[:10],
            "found": NOW.isoformat(), "score": s + bonus, "tags": tags,
            # 详情讲解增强需要比列表摘要更完整的依据；页面端仍只展示前 200 字。
            "summary_en": re.sub(r"\s+", " ", (body or "").strip())[:2000],
            "summary_zh": "", "demo": "", "stars": stars}


# ---------------------------------------------------------------------------
# 四个源
# ---------------------------------------------------------------------------
def src_arxiv():
    """arXiv Atom API。按核心短语查最近提交，类别限制在语音/NLP/CV/AI。"""
    out, ns = [], {"a": "http://www.w3.org/2005/Atom"}
    cats = "(cat:cs.CL OR cat:cs.SD OR cat:eess.AS OR cat:cs.CV OR cat:cs.AI)"
    queries = ['all:"full-duplex"', 'all:"speech-to-speech"',
               'all:"spoken dialogue" AND all:streaming',
               'all:"voice assistant"', 'abs:omni AND abs:multimodal']
    queries += ['all:"multimodal agent"', 'all:"audio-visual agent"',
                'all:"native audio" AND all:multimodal',
                'all:"vision-language-action"',
                'all:"real-time multimodal"']
    for q in queries:
        url = ("https://export.arxiv.org/api/query?search_query="
               + urllib.parse.quote(f"({q}) AND {cats}")
               + "&sortBy=submittedDate&sortOrder=descending&max_results=20")
        for e in ET.fromstring(http_get(url)).findall("a:entry", ns):
            title = e.findtext("a:title", "", ns)
            link = e.findtext("a:id", "", ns)
            out.append(mk("paper", "arxiv", title, link,
                          e.findtext("a:published", "", ns),
                          e.findtext("a:summary", "", ns)))
    return out


def src_github():
    """GitHub 仓库搜索。带 GITHUB_TOKEN 时限额更高（Actions 里自动有）。"""
    out = []
    h = {"Accept": "application/vnd.github+json"}
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        h["Authorization"] = "Bearer " + tok
    queries = ["full-duplex in:name,description,topics",
               '"speech-to-speech" in:name,description,topics',
               "omni multimodal in:name,description,topics",
               "voice agent llm in:name,description,topics",
               '"multimodal agent" in:name,description,topics',
               '"audio visual" agent in:name,description,topics',
               '"vision language action" in:name,description,topics',
               '"native audio" model in:name,description,topics']
    for q in queries:
        url = ("https://api.github.com/search/repositories?q="
               + urllib.parse.quote(q) + "&sort=updated&order=desc&per_page=15")
        for r in http_json(url, h).get("items", []):
            if (r.get("stargazers_count") or 0) < 3:
                continue
            body = (r.get("description") or "") + " " + " ".join(r.get("topics") or [])
            out.append(mk("repo", "github", r["full_name"], r["html_url"],
                          (r.get("pushed_at") or ""), body,
                          stars=r.get("stargazers_count")))
    return out


def src_hf():
    """HuggingFace：daily papers（编辑精选，+2 分）+ omni 相关模型。"""
    out = []
    for p in http_json("https://huggingface.co/api/daily_papers?limit=50"):
        pp = p.get("paper") or {}
        if not pp.get("id"):
            continue
        out.append(mk("paper", "hf", pp.get("title", ""),
                      "https://huggingface.co/papers/" + pp["id"],
                      (p.get("publishedAt") or ""), pp.get("summary", ""), bonus=2))
    for term in ("omni", "multimodal agent", "audio visual", "native audio",
                 "vision language action"):
        url = ("https://huggingface.co/api/models?search="
               + urllib.parse.quote(term)
               + "&sort=lastModified&direction=-1&limit=15")
        for m in http_json(url):
            mid = m.get("modelId") or m.get("id") or ""
            if not mid:
                continue
            body = ((m.get("pipeline_tag") or "") + " "
                    + " ".join(m.get("tags") or []))
            out.append(mk("model", "hf", mid, "https://huggingface.co/" + mid,
                          (m.get("lastModified") or ""), body,
                          stars=m.get("likes")))
    return out


def src_hn():
    """HackerNews (Algolia)。新闻噪声大：只收 3 分以上的 story。"""
    out = []
    for q in ["full-duplex", "speech-to-speech", "voice agent", "realtime voice"]:
        url = ("https://hn.algolia.com/api/v1/search_by_date?query="
               + urllib.parse.quote(q)
               + "&tags=story&numericFilters=points>2&hitsPerPage=10")
        for hit in http_json(url).get("hits", []):
            link = hit.get("url") or ("https://news.ycombinator.com/item?id="
                                      + str(hit.get("objectID")))
            out.append(mk("news", "hn", hit.get("title", ""), link,
                          (hit.get("created_at") or ""),
                          hit.get("story_text") or "",
                          stars=hit.get("points")))
    return out


# 各源入库门槛（分数低于此丢弃）。HF daily 有人工精选背书，门槛最低。
THRESH = {"arxiv": 4, "github": 4, "hf": 3, "hn": 4}


def merge_items(items, fresh, new_limit=15, inventory_limit=500):
    """更新全部旧命中，再从真正的新 URL 中取高分项，避免旧高分项饿死新增。

    同一轮四个来源可能重复返回同一 URL；新候选先按 URL 去重并保留高分版本。
    """
    by_url = {it["url"]: it for it in items}
    new_by_url, updated_urls = {}, set()
    for incoming in fresh:
        old = by_url.get(incoming["url"])
        if old:
            old["score"] = max(old.get("score", 0), incoming.get("score", 0))
            if incoming.get("stars") is not None:
                old["stars"] = incoming["stars"]
            updated_urls.add(incoming["url"])
            continue
        previous = new_by_url.get(incoming["url"])
        if previous is None or incoming.get("score", 0) > previous.get("score", 0):
            new_by_url[incoming["url"]] = incoming

    admitted = sorted(
        new_by_url.values(),
        key=lambda row: (-row.get("score", 0), row.get("url", "")),
    )[:new_limit]
    for item in admitted:
        by_url[item["url"]] = item
    merged = sorted(
        by_url.values(), key=lambda row: row.get("found", ""), reverse=True
    )[:inventory_limit]
    return merged, len(admitted), len(updated_urls), len(new_by_url)


def main():
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    try:
        items = json.load(open(DATA, encoding="utf-8"))["items"]
    except Exception:
        items = []
    fresh, fails = [], []
    for name, fn in [("arxiv", src_arxiv), ("github", src_github),
                     ("hf", src_hf), ("hn", src_hn)]:
        try:
            got = fn()
            kept = [x for x in got if x["score"] >= THRESH[name]]
            fresh += kept
            print(f"[{name}] 抓到 {len(got)}，过门槛 {len(kept)}")
        except Exception as e:
            fails.append(name)
            print(f"[{name}] 失败: {type(e).__name__}: {str(e)[:120]}")

    # 单轮入库上限刻意压低：一是控制每天的阅读量（用户在按天学习，一天灌
    # 100+ 条是轰炸不是雷达）；二是让冷启动积压的高分老内容按 score 从高到
    # 低分几天匀速放出。关键：上限只作用于去重后的“真正新条目”，不能让每轮
    # 都出现的旧高分结果占满 15 个名额，否则新论文会永久饥饿。
    items, added, updated, candidates = merge_items(items, fresh)
    json.dump({"generated": NOW.isoformat(), "items": items},
              open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"新增 {added}/{candidates} 候选，更新 {updated}，库存 {len(items)}"
          + (f"，失败源: {fails}" if fails else ""))
    # 全源失败才算这次运行失败（部分失败下次会补上）
    return 1 if len(fails) == 4 else 0


if __name__ == "__main__":
    sys.exit(main())
