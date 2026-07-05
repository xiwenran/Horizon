"""Export high personal relevance items to a local Obsidian vault."""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path
from typing import Sequence

from ..models import ContentItem, ObsidianExportConfig

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_BEGIN = "<!-- horizon:auto:start -->"
_END = "<!-- horizon:auto:end -->"


class ObsidianExporter:
    """Write a compact daily note for highly personally relevant items."""

    def __init__(self, config: ObsidianExportConfig):
        self.config = config

    def write(self, items: Sequence[ContentItem], *, date: str) -> Path | None:
        if not self.config.enabled:
            return None

        selected = [
            item for item in items
            if (item.personal_score or 0) >= self.config.personal_score_threshold
        ]
        if not selected:
            return None

        output_dir = Path(self.config.vault_path).expanduser() / self.config.relative_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{date}.md"
        block = self._render_block(selected, date=date)

        if output_path.exists():
            current = output_path.read_text(encoding="utf-8")
            if _BEGIN in current and _END in current:
                before, rest = current.split(_BEGIN, 1)
                _, after = rest.split(_END, 1)
                content = before.rstrip() + "\n\n" + block + "\n" + after.lstrip()
            else:
                content = current.rstrip() + "\n\n" + block + "\n"
        else:
            content = self._frontmatter(date) + "\n\n" + block + "\n"

        output_path.write_text(content, encoding="utf-8")
        return output_path

    def _frontmatter(self, date: str) -> str:
        return (
            "---\n"
            f"title: Horizon 信息雷达 {date}\n"
            f"date: {date}\n"
            "type: decision\n"
            "project: Horizon\n"
            "tags: [Horizon, 信息雷达, AI筛选]\n"
            "status: done\n"
            "---"
        )

    def _render_block(self, items: Sequence[ContentItem], *, date: str) -> str:
        threshold = f"{self.config.personal_score_threshold:g}"
        lines = [
            _BEGIN,
            f"## {date} 高价值更新",
            "",
            f"只保留个人相关分 {threshold} 分以上的内容，便于后续复盘和行动。",
            "",
        ]
        for item in items:
            title = _clip(_title(item), 60)
            lines.extend(
                [
                    f"### {title}",
                    f"- 价值点：{_clip(_value(item), 30)}",
                    f"- 摘要：{_clip(_summary(item), 50)}",
                    f"- 来源：{_source(item)}",
                    f"- 原文：{item.url}",
                    f"- 标签：{', '.join(_tags(item)) or '未标注'}",
                    "",
                ]
            )
        lines.append(_END)
        return "\n".join(lines)


def _title(item: ContentItem) -> str:
    return _first_text(
        item.metadata.get("title_zh"),
        item.metadata.get("zh_title"),
        item.title,
        item.ai_summary,
        fallback="未命名更新",
    )


def _summary(item: ContentItem) -> str:
    return _first_text(
        item.metadata.get("detailed_summary_zh"),
        item.metadata.get("summary_zh"),
        item.ai_summary,
        item.content,
        fallback="打开原文查看上下文。",
    )


def _value(item: ContentItem) -> str:
    return _first_text(
        item.personal_reason_zh,
        item.suggested_action_zh,
        fallback="与当前项目方向相关。",
    )


def _source(item: ContentItem) -> str:
    metadata = item.metadata
    for key in ("feed_name", "source_name", "repo", "subreddit", "watchlist"):
        if metadata.get(key):
            return str(metadata[key])
    return item.author or item.source_type.value


def _tags(item: ContentItem) -> list[str]:
    raw_tags = [*(item.ai_tags or []), *(item.metadata.get("tags") or [])]
    tags: list[str] = []
    for raw in raw_tags:
        tag = _clean(str(raw))
        if tag and tag not in tags:
            tags.append(tag)
        if len(tags) == 5:
            break
    return tags


def _first_text(*values: object, fallback: str) -> str:
    for value in values:
        cleaned = _clean(str(value or ""))
        if cleaned:
            return cleaned
    return fallback


def _clean(value: str) -> str:
    return _SPACE_RE.sub(" ", unescape(_TAG_RE.sub(" ", value))).strip()


def _clip(value: str, limit: int) -> str:
    cleaned = _clean(value)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."
