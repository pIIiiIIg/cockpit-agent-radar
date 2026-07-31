#!/usr/bin/env python3
"""列出尚未生成深度讲解的论文，供 Cursor 自动化与人工补录使用。"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(ROOT, "data", "items.json"), encoding="utf-8") as stream:
    items = json.load(stream)["items"]
with open(os.path.join(ROOT, "data", "explanations.json"), encoding="utf-8") as stream:
    explanations = json.load(stream)

for item in items:
    if item["kind"] == "paper" and item["id"] not in explanations:
        print(f"{item['id']}\t{item['found'][:10]}\t{item['title']}\t{item['url']}")
