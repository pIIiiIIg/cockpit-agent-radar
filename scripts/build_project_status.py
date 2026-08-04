#!/usr/bin/env python3
"""Create a public-safe project snapshot from StreamingModelHarness origin/main."""
import argparse
import datetime as dt
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GIT = (os.environ.get("GIT_BIN") or shutil.which("git")
       or r"C:\Program Files\Git\cmd\git.exe")


def git(repo, *args, check=True):
    result = subprocess.run(
        [GIT, "-C", str(repo), *args],
        text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout


def show(repo, path):
    return git(repo, "show", f"origin/main:{path}", check=False)


def section(markdown, heading):
    start = markdown.find(heading)
    if start < 0:
        return ""
    tail = markdown[start:]
    next_heading = tail.find("\n## ", len(heading))
    return tail if next_heading < 0 else tail[:next_heading]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        default=os.environ.get(
            "STREAMING_HARNESS_REPO",
            r"C:\Users\Administrator\Projects\StreamingModelHarness"),
    )
    parser.add_argument(
        "--output",
        default=str(ROOT / "project_status" / "StreamingModelHarness.md"),
    )
    args = parser.parse_args()
    source = Path(args.source)
    if not (source / ".git").exists():
        raise SystemExit(f"source repository not found: {source}")
    git(source, "fetch", "origin")
    commits = git(
        source, "log", "origin/main", "-15",
        "--format=- `%h` %ad %s", "--date=iso")
    readme = show(source, "README.md")
    known = section(readme, "## 已知问题")
    if not known:
        known = section(readme, "## 已知短板")
    matrix = show(source, "docs/DESIGN_DIMENSIONS.md")
    remote_result = show(source, "bench/RESULTS_H20_2026-08-03.md")
    local_result = source / "bench" / "RESULTS_H20_2026-08-03.md"
    result_text = remote_result
    if not result_text and local_result.exists():
        result_text = local_result.read_text(encoding="utf-8")
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    body = [
        "# StreamingModelHarness 项目状态快照",
        "",
        f"生成时间：{now}",
        "",
        "> 只包含公开技术进展、基准和问题，不包含密钥、服务器地址或运行凭据。",
        "",
        "## 最近提交",
        "",
        commits.strip() or "暂无可读取提交。",
        "",
        "## 当前已知问题",
        "",
        known.strip() or "README 未提取到已知问题章节。",
    ]
    if result_text:
        body += ["", "## 最近基准", "", result_text.strip()]
    if matrix:
        body += ["", "## 设计维度摘录", "", matrix[:12000].strip()]
    output.write_text("\n".join(body) + "\n", encoding="utf-8")
    print(f"project status written: {output}")


if __name__ == "__main__":
    main()
