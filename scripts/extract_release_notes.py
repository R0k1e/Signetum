#!/usr/bin/env python3
"""
从 CHANGELOG.md 或 git tag 注释提取发布说明。

使用方式:
    python scripts/extract_release_notes.py <version> <output_file>

例如:
    python scripts/extract_release_notes.py v1.0.0 RELEASE_NOTES.md
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


def extract_from_changelog(version: str) -> str | None:
    """从 CHANGELOG.md 提取指定版本的发布说明。"""
    changelog_path = Path("CHANGELOG.md")
    if not changelog_path.exists():
        return None

    # 支持 v1.0.0 或 1.0.0 格式
    version_clean = version.lstrip("v")
    patterns = [
        rf"^## \[{re.escape(version)}\]",  # ## [v1.0.0]
        rf"^## \[{re.escape(version_clean)}\]",  # ## [1.0.0]
    ]

    with changelog_path.open(encoding="utf-8") as f:
        lines = f.readlines()

    capture = False
    result_lines = []

    for line in lines:
        # 检查是否匹配版本标题
        if any(re.match(pattern, line) for pattern in patterns):
            capture = True
            continue

        # 如果遇到下一个版本标题，停止捕获
        if capture and line.startswith("## ["):
            break

        # 捕获内容
        if capture:
            result_lines.append(line)

    if result_lines:
        return "".join(result_lines).strip()

    return None


def extract_from_git_tag(version: str) -> str | None:
    """从 git tag 注释提取发布说明。"""
    try:
        # 获取 tag 注释
        result = subprocess.run(
            ["git", "tag", "-l", "--format=%(contents)", version],
            capture_output=True,
            text=True,
            check=True,
        )
        tag_message = result.stdout.strip()

        if tag_message:
            return tag_message
    except subprocess.CalledProcessError:
        pass

    return None


def main() -> None:
    """主函数。"""
    parser = argparse.ArgumentParser(
        description="从 CHANGELOG.md 或 git tag 提取发布说明",
    )
    parser.add_argument("version", help="版本号，例如 'v1.0.0'")
    parser.add_argument("output_file", help="输出文件路径")
    args = parser.parse_args()

    # 尝试从 CHANGELOG.md 提取
    release_notes = extract_from_changelog(args.version)

    # 如果未找到，尝试从 git tag 提取
    if not release_notes:
        release_notes = extract_from_git_tag(args.version)

    # 如果都没找到，报错并退出
    if not release_notes:
        print(
            f"❌ 错误：未找到版本 {args.version} 的发布说明。",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        print("请使用以下两种方式之一设置发布说明：", file=sys.stderr)
        print("", file=sys.stderr)
        print("方式 1：创建带注释的 git tag", file=sys.stderr)
        print(
            f'  git tag -a {args.version} -m "发布说明内容"',
            file=sys.stderr,
        )
        print(f"  git push origin {args.version}", file=sys.stderr)
        print("", file=sys.stderr)
        print("方式 2：在 CHANGELOG.md 中添加版本条目", file=sys.stderr)
        print("  格式示例：", file=sys.stderr)
        print(f"  ## [{args.version}] - YYYY-MM-DD", file=sys.stderr)
        print("  ", file=sys.stderr)
        print("  ### 新功能", file=sys.stderr)
        print("  - 添加了 XXX 功能", file=sys.stderr)
        print("  ", file=sys.stderr)
        print("  ### 修复", file=sys.stderr)
        print("  - 修复了 YYY 问题", file=sys.stderr)
        sys.exit(1)

    # 写入输出文件
    output_path = Path(args.output_file)
    output_path.write_text(release_notes, encoding="utf-8")
    print(f"✅ 成功提取发布说明到 {args.output_file}")


if __name__ == "__main__":
    main()

