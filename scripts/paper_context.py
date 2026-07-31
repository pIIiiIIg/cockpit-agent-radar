#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为论文讲解提取可引用的公开正文和项目链接（零第三方依赖）。

抓取失败时回落到 items.json 已有摘要；增强通道因此永远不会阻塞建站。
"""
import html
import re
import urllib.request
from html.parser import HTMLParser

UA = {"User-Agent": "cockpit-agent-radar/1.1 (+github.com/pIIiiIIg/cockpit-agent-radar)"}
MAX_CONTEXT = 24000
_ARXIV = re.compile(r"(?:arxiv\.org/(?:abs|html)/|huggingface\.co/papers/)(\d{4}\.\d{4,5})(?:v\d+)?")
_USEFUL_LINK = re.compile(
    r"^https://(?:github\.com|huggingface\.co|modelscope\.cn|www\.modelscope\.cn)/",
    re.I,
)


class PaperHTML(HTMLParser):
    """保留标题、正文、列表和表格文本；丢掉公式、导航和脚本噪声。"""

    BLOCKS = {"h1", "h2", "h3", "h4", "p", "li", "figcaption", "th", "td"}
    SKIP = {"script", "style", "svg", "math", "nav", "footer"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.links = []
        self._skip = 0
        self._block = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in self.SKIP:
            self._skip += 1
        if tag in self.BLOCKS:
            self._block += 1
        if tag == "a":
            href = dict(attrs).get("href", "")
            if href.startswith("//"):
                href = "https:" + href
            if _USEFUL_LINK.match(href):
                self.links.append(href.rstrip("/"))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.BLOCKS and self._block:
            self._block -= 1
            self.parts.append("\n")
        if tag in self.SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and self._block:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.parts.append(text + " ")

    def result(self):
        text = html.unescape("".join(self.parts))
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return text, list(dict.fromkeys(self.links))[:12]


def _select_context(text):
    """长论文兼顾开头、方法、实验和结论，不只机械截取前 24k。"""
    if len(text) <= MAX_CONTEXT:
        return text
    chunks = [text[:7000]]
    heading = re.compile(
        r"(?im)^(?:\d+(?:\.\d+)*\s+)?"
        r"(?:method|approach|architecture|implementation|experiment|evaluation|"
        r"result|ablation|limitation|discussion|conclusion)s?\b.*$")
    for match in heading.finditer(text):
        chunk = text[match.start():match.start() + 3500]
        if chunk and all(chunk[:160] not in old for old in chunks):
            chunks.append(chunk)
        if sum(len(old) for old in chunks) >= MAX_CONTEXT:
            break
    return "\n\n".join(chunks)[:MAX_CONTEXT]


def _get(url, timeout=45):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def paper_context(item):
    """返回 {depth,text,links}；depth 为 fulltext 或 abstract。"""
    fallback = (item.get("summary_en") or "").strip()
    match = _ARXIV.search(item.get("url") or "")
    if not match:
        return {"depth": "abstract", "text": fallback, "links": []}

    arxiv_id = match.group(1)
    try:
        parser = PaperHTML()
        parser.feed(_get(f"https://arxiv.org/html/{arxiv_id}"))
        text, links = parser.result()
        if len(text) >= 1000:
            return {"depth": "fulltext", "text": _select_context(text), "links": links}
    except Exception as exc:
        print(f"  fulltext {arxiv_id} 获取失败，回落摘要: {type(exc).__name__}")
    return {"depth": "abstract", "text": fallback, "links": []}
