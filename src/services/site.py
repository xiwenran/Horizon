"""Static local site generator for the daily Horizon digest."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from html import escape, unescape
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urlparse

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None  # type: ignore[assignment]

from ..models import ContentItem


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_MAX_ITEMS = 20


class LocalSiteGenerator:
    """Render a self-contained light themed HTML digest."""

    def __init__(self, output_dir: Path | str, timezone_name: str = "Asia/Shanghai"):
        self.output_dir = Path(output_dir)
        self.timezone = _load_timezone(timezone_name)

    def write(
        self,
        items: Sequence[ContentItem],
        *,
        date: str,
        total_items: int,
        generated_at: datetime | None = None,
    ) -> Path:
        """Generate ``index.html`` and return its path."""
        generated_at = generated_at or datetime.now(timezone.utc)
        selected_items = _sort_items(items)[:_MAX_ITEMS]
        html = self.render(
            selected_items,
            date=date,
            total_items=total_items,
            generated_at=generated_at,
        )

        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / "index.html"
        output_path.write_text(html, encoding="utf-8")
        return output_path

    def render(
        self,
        items: Sequence[ContentItem],
        *,
        date: str,
        total_items: int,
        generated_at: datetime,
    ) -> str:
        selected_count = len(items)
        display_date = _format_date(date)
        updated_at = _format_datetime(generated_at, self.timezone)
        cards = "\n".join(
            self._render_card(index, item) for index, item in enumerate(items, start=1)
        )
        if not cards:
            cards = """
            <section class="empty-state">
              <p>今天还没有进入精选的内容。</p>
            </section>
            """.strip()

        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>视野日报 - {escape(display_date)}</title>
  <style>
    :root {{
      --paper: #f5f7fb;
      --ink: #111827;
      --muted: #667085;
      --faint: #98a2b3;
      --line: rgba(21, 32, 50, 0.1);
      --glass: rgba(255, 255, 255, 0.72);
      --glass-strong: rgba(255, 255, 255, 0.88);
      --blue: #0071e3;
      --sky: #5ac8fa;
      --mint: #34c759;
      --pink: #ff7eb6;
      --amber: #ffb340;
      --violet: #8e8cf0;
      --shadow: 0 22px 58px rgba(28, 39, 64, 0.12);
      --shadow-hover: 0 34px 86px rgba(28, 39, 64, 0.18);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background:
        linear-gradient(115deg, rgba(90, 200, 250, 0.22), transparent 34%),
        linear-gradient(245deg, rgba(255, 126, 182, 0.16), transparent 38%),
        linear-gradient(180deg, #fafdff 0, #f5f8ff 43%, #f7f7fb 100%),
        var(--paper);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      font-size: 16px;
      letter-spacing: 0;
      min-height: 100vh;
    }}

    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: 0.52;
      background-image:
        linear-gradient(180deg, rgba(255, 255, 255, 0.72), transparent 34%),
        repeating-linear-gradient(90deg, rgba(255, 255, 255, 0.22) 0 1px, transparent 1px 7px);
      mask-image: linear-gradient(180deg, #000 0, transparent 74%);
    }}

    a {{
      color: inherit;
      text-decoration: none;
    }}

    .page {{
      position: relative;
      width: min(100%, 1120px);
      margin: 0 auto;
      padding: 36px 24px 80px;
    }}

    .masthead {{
      position: sticky;
      top: 0;
      z-index: 5;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 28px;
      align-items: end;
      padding: 28px 0 30px;
      border-bottom: 1px solid rgba(21, 32, 50, 0.08);
      background: linear-gradient(180deg, rgba(250, 252, 255, 0.9), rgba(250, 252, 255, 0.64));
      backdrop-filter: blur(24px) saturate(1.45);
      -webkit-backdrop-filter: blur(24px) saturate(1.45);
    }}

    .brand {{
      display: inline-flex;
      align-items: center;
      gap: 9px;
      margin: 0 0 18px;
      color: #344054;
      font-size: 0.78rem;
      font-weight: 800;
      letter-spacing: 0.08em;
    }}

    .brand::before {{
      content: "";
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: linear-gradient(135deg, var(--blue), var(--sky) 44%, var(--pink));
      box-shadow: 0 0 0 6px rgba(0, 113, 227, 0.1);
    }}

    h1 {{
      max-width: 760px;
      margin: 0;
      font-size: 3.56rem;
      line-height: 1.04;
      font-weight: 800;
      letter-spacing: 0;
      background: linear-gradient(95deg, #101828 0, #1d4ed8 43%, #9b3f7f 86%);
      -webkit-background-clip: text;
      background-clip: text;
      color: transparent;
    }}

    .lead {{
      max-width: 680px;
      margin: 16px 0 0;
      color: var(--muted);
      font-size: 1.06rem;
      line-height: 1.72;
    }}

    .stats {{
      min-width: 236px;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      border: 1px solid rgba(255, 255, 255, 0.76);
      border-radius: 8px;
      overflow: hidden;
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(246, 249, 255, 0.62));
      box-shadow: 0 18px 44px rgba(28, 39, 64, 0.1);
      backdrop-filter: blur(20px) saturate(1.3);
      -webkit-backdrop-filter: blur(20px) saturate(1.3);
    }}

    .stat {{
      padding: 14px 16px;
      border-right: 1px solid rgba(21, 32, 50, 0.08);
    }}

    .stat:nth-child(2n) {{
      border-right: 0;
    }}

    .stat span {{
      display: block;
      color: var(--muted);
      font-size: 0.78rem;
      line-height: 1.4;
    }}

    .stat strong {{
      display: block;
      margin-top: 4px;
      font-size: 1rem;
      line-height: 1.35;
      font-weight: 800;
    }}

    .story-list {{
      display: grid;
      gap: 14px;
      margin-top: 30px;
    }}

    .story {{
      --accent: var(--blue);
      --accent-soft: rgba(0, 113, 227, 0.13);
      position: relative;
      display: grid;
      grid-template-columns: 64px 1fr;
      gap: 18px;
      min-height: 148px;
      padding: 22px;
      border: 1px solid rgba(255, 255, 255, 0.78);
      border-radius: 8px;
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.92), rgba(255, 255, 255, 0.7)),
        linear-gradient(110deg, var(--accent-soft), transparent 34%);
      box-shadow: var(--shadow);
      overflow: hidden;
      opacity: 0;
      transform: translateY(18px) scale(0.988);
      animation: cardIn 700ms cubic-bezier(0.2, 0.92, 0.2, 1) forwards;
      animation-delay: calc(var(--i) * 52ms);
      backdrop-filter: blur(20px) saturate(1.35);
      -webkit-backdrop-filter: blur(20px) saturate(1.35);
      transition:
        transform 240ms cubic-bezier(0.2, 0.92, 0.2, 1),
        border-color 240ms ease,
        box-shadow 240ms ease,
        background 240ms ease;
      will-change: transform;
    }}

    .story:nth-child(4n + 1) {{
      --accent: var(--blue);
      --accent-soft: rgba(0, 113, 227, 0.13);
    }}

    .story:nth-child(4n + 2) {{
      --accent: var(--pink);
      --accent-soft: rgba(255, 126, 182, 0.14);
    }}

    .story:nth-child(4n + 3) {{
      --accent: var(--mint);
      --accent-soft: rgba(52, 199, 89, 0.13);
    }}

    .story:nth-child(4n) {{
      --accent: var(--violet);
      --accent-soft: rgba(142, 140, 240, 0.14);
    }}

    .story::before {{
      content: "";
      position: absolute;
      inset: 0;
      padding: 1px;
      border-radius: inherit;
      background: linear-gradient(135deg, rgba(255, 255, 255, 0.96), var(--accent), rgba(255, 255, 255, 0.72));
      opacity: 0.58;
      pointer-events: none;
      mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
      mask-composite: exclude;
      -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
      -webkit-mask-composite: xor;
    }}

    .story::after {{
      content: "";
      position: absolute;
      top: -32%;
      bottom: -32%;
      left: -42%;
      width: 34%;
      pointer-events: none;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.72), transparent);
      opacity: 0;
      transform: rotate(12deg);
      transition: left 520ms cubic-bezier(0.2, 0.92, 0.2, 1), opacity 220ms ease;
    }}

    .story:hover {{
      transform: translateY(-7px) scale(1.006);
      border-color: color-mix(in srgb, var(--accent) 34%, #ffffff);
      background:
        linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(249, 252, 255, 0.82)),
        linear-gradient(110deg, var(--accent-soft), transparent 38%);
      box-shadow: var(--shadow-hover);
    }}

    .story:hover::after {{
      left: 112%;
      opacity: 1;
    }}

    .story:focus-within {{
      outline: 3px solid rgba(0, 113, 227, 0.22);
      outline-offset: 3px;
    }}

    .story-number {{
      display: grid;
      place-items: center;
      width: 54px;
      height: 54px;
      border: 1px solid color-mix(in srgb, var(--accent) 24%, #ffffff);
      border-radius: 50%;
      color: var(--accent);
      background:
        linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(255, 255, 255, 0.62)),
        color-mix(in srgb, var(--accent) 9%, #ffffff);
      font-size: 1.2rem;
      font-weight: 800;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9), 0 12px 28px rgba(28, 39, 64, 0.08);
      transition: transform 220ms ease, background 220ms ease, box-shadow 220ms ease;
    }}

    .story:hover .story-number {{
      transform: translateY(-2px) scale(1.06);
      background:
        linear-gradient(180deg, color-mix(in srgb, var(--accent) 18%, #ffffff), #ffffff);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.95), 0 18px 34px rgba(28, 39, 64, 0.13);
    }}

    .story-main {{
      min-width: 0;
    }}

    .story-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-bottom: 12px;
      color: var(--muted);
      font-size: 0.82rem;
      line-height: 1.45;
    }}

    .source {{
      color: var(--ink);
      font-weight: 800;
    }}

    .meta-dot {{
      color: var(--faint);
    }}

    .category {{
      padding: 3px 9px;
      border: 1px solid color-mix(in srgb, var(--accent) 24%, #ffffff);
      border-radius: 999px;
      background: color-mix(in srgb, var(--accent) 11%, #ffffff);
      color: var(--accent);
      font-size: 0.76rem;
      font-weight: 700;
    }}

    h2 {{
      margin: 0;
      font-size: 1.2rem;
      line-height: 1.48;
      letter-spacing: 0;
      transition: color 180ms ease;
    }}

    .story:hover h2 {{
      color: color-mix(in srgb, var(--accent) 72%, #111827);
    }}

    .summary {{
      margin: 10px 0 0;
      color: #4b5565;
      line-height: 1.82;
    }}

    .footer-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin-top: 16px;
    }}

    .tag {{
      padding: 4px 9px;
      border-radius: 999px;
      font-size: 0.76rem;
      font-weight: 700;
      border: 1px solid rgba(255, 255, 255, 0.72);
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.78);
    }}

    .tag:nth-child(5n + 1) {{
      background: #e8f3ff;
      color: #0068d8;
    }}

    .tag:nth-child(5n + 2) {{
      background: #fff3dd;
      color: var(--amber);
    }}

    .tag:nth-child(5n + 3) {{
      background: #f0efff;
      color: var(--violet);
    }}

    .tag:nth-child(5n + 4) {{
      background: #ffeaf3;
      color: #d94886;
    }}

    .tag:nth-child(5n) {{
      background: #e9f8ef;
      color: #178a3f;
    }}

    .open-link {{
      margin-left: auto;
      padding: 7px 13px;
      border-radius: 999px;
      background: color-mix(in srgb, var(--accent) 10%, #ffffff);
      color: var(--accent);
      font-size: 0.84rem;
      font-weight: 800;
      transition: transform 180ms ease, background 180ms ease, color 180ms ease;
    }}

    .open-link::after {{
      content: "→";
      display: inline-block;
      margin-left: 6px;
      transition: transform 160ms ease;
    }}

    .open-link:hover::after {{
      transform: translateX(3px);
    }}

    .story:hover .open-link {{
      transform: translateY(-1px);
      background: var(--accent);
      color: #ffffff;
    }}

    .empty-state {{
      margin-top: 28px;
      padding: 36px 22px;
      border: 1px dashed var(--line);
      border-radius: 8px;
      background: var(--glass);
      color: var(--muted);
      text-align: center;
      backdrop-filter: blur(18px);
      -webkit-backdrop-filter: blur(18px);
    }}

    @keyframes cardIn {{
      from {{
        opacity: 0;
        transform: translateY(16px) scale(0.985);
      }}
      to {{
        opacity: 1;
        transform: translateY(0) scale(1);
      }}
    }}

    @media (prefers-reduced-motion: reduce) {{
      .story {{
        animation: none;
        opacity: 1;
        transform: none;
      }}

      .story,
      .story::after,
      .story-number,
      .open-link,
      .open-link::after {{
        transition: none;
      }}
    }}

    @media (max-width: 760px) {{
      .page {{
        padding: 30px 16px 56px;
      }}

      .masthead {{
        grid-template-columns: 1fr;
        align-items: start;
        position: static;
      }}

      h1 {{
        font-size: 2.38rem;
      }}

      .stats {{
        width: 100%;
      }}

      .story {{
        grid-template-columns: 44px 1fr;
        gap: 12px;
        padding: 18px 15px;
      }}

      .story-number {{
        width: 40px;
        height: 40px;
        font-size: 1rem;
      }}

      h2 {{
        font-size: 1.04rem;
      }}

      .open-link {{
        width: 100%;
        margin-left: 0;
        text-align: center;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <header class="masthead">
      <div>
        <p class="brand">视野日报</p>
        <h1>{escape(display_date)} 信息简报</h1>
        <p class="lead">从订阅源里挑出值得看的更新，整理成中文摘要，保留来源和原文入口，适合每天快速扫一遍。</p>
      </div>
      <aside class="stats" aria-label="日报统计">
        <div class="stat">
          <span>精选</span>
          <strong>{selected_count} / {total_items}</strong>
        </div>
        <div class="stat">
          <span>更新</span>
          <strong>{escape(updated_at)}</strong>
        </div>
      </aside>
    </header>
    <section class="story-list" aria-label="精选内容">
      {cards}
    </section>
  </main>
</body>
</html>
"""

    def _render_card(self, index: int, item: ContentItem) -> str:
        title = _best_title(item)
        detail = _best_detail(item)
        if detail == title:
            detail = _best_detail(item, skip_title=True)
        detail = _clip(detail, 190)
        source = _source_label(item)
        category = _category_label(item)
        published = _format_datetime(item.published_at, self.timezone)
        score = f"{item.ai_score:.1f}" if item.ai_score is not None else "-"
        tags = _tags(item)
        tags_html = "\n".join(f'<span class="tag">{escape(tag)}</span>' for tag in tags)
        category_html = f'<span class="category">{escape(category)}</span>' if category else ""

        return f"""
      <article class="story" style="--i: {index}">
        <a class="story-number" href="{escape(str(item.url), quote=True)}" target="_blank" rel="noopener noreferrer" aria-label="打开第 {index:02d} 条原文">{index:02d}</a>
        <div class="story-main">
          <div class="story-meta">
            <span class="source">{escape(source)}</span>
            {category_html}
            <span class="meta-dot">·</span>
            <span>{escape(published)}</span>
            <span class="meta-dot">·</span>
            <span>评分 {escape(score)}</span>
          </div>
          <h2><a href="{escape(str(item.url), quote=True)}" target="_blank" rel="noopener noreferrer">{escape(_clip(title, 118))}</a></h2>
          <p class="summary">{escape(detail)}</p>
          <div class="footer-row">
            {tags_html}
            <a class="open-link" href="{escape(str(item.url), quote=True)}" target="_blank" rel="noopener noreferrer">打开原文</a>
          </div>
        </div>
      </article>
""".rstrip()


def _load_timezone(timezone_name: str) -> timezone:
    if ZoneInfo is not None:
        try:
            return ZoneInfo(timezone_name)  # type: ignore[return-value]
        except Exception:
            pass
    return timezone(timedelta(hours=8))


def _sort_items(items: Sequence[ContentItem]) -> list[ContentItem]:
    return sorted(
        items,
        key=lambda item: (_score(item), _timestamp(item.published_at)),
        reverse=True,
    )


def _score(item: ContentItem) -> float:
    return item.ai_score if item.ai_score is not None else -1.0


def _timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _format_date(date: str) -> str:
    try:
        parsed = datetime.strptime(date, "%Y-%m-%d")
        return parsed.strftime("%Y.%m.%d")
    except ValueError:
        return date


def _format_datetime(value: datetime, tz: timezone) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local_value = value.astimezone(tz)
    return local_value.strftime("%m.%d %H:%M")


def _first_text(*values: str | None, fallback: str) -> str:
    for value in values:
        cleaned = _clean_text(value or "")
        if cleaned:
            return cleaned
    return fallback


def _best_title(item: ContentItem) -> str:
    metadata = item.metadata
    title = _first_chinese_text(
        _metadata_text(metadata, "title_zh", "zh_title", "translated_title", "title_cn"),
        item.ai_summary,
        item.title,
        item.content,
    )
    if title:
        return _clip(title, 86)

    raw_title = _clean_text(item.title).lower()
    common_titles = {
        "action!": "开始行动",
        "cables management": "线缆整理",
        "you can just cook things": "直接动手做就行",
    }
    if raw_title in common_titles:
        return common_titles[raw_title]

    return "短动态：查看原文"


def _best_detail(item: ContentItem, *, skip_title: bool = False) -> str:
    metadata = item.metadata
    candidates = [
        _metadata_text(
            metadata,
            "detailed_summary_zh",
            "summary_zh",
            "zh_summary",
            "translated_summary",
            "background_zh",
            "community_discussion_zh",
        ),
        item.ai_reason,
        None if skip_title else item.ai_summary,
        item.content,
    ]
    detail = _first_chinese_text(*candidates)
    if detail:
        return detail

    return "原文内容较短，建议打开原文查看图片或上下文。"


def _metadata_text(metadata: dict, *keys: str) -> str:
    for key in keys:
        value = metadata.get(key)
        cleaned = _clean_text(str(value)) if value is not None else ""
        if cleaned:
            return cleaned
    return ""


def _first_chinese_text(*values: str | None) -> str:
    for value in values:
        cleaned = _clean_text(value or "")
        if cleaned and _has_cjk(cleaned):
            return cleaned
    return ""


def _has_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _clean_text(value: str) -> str:
    without_tags = _TAG_RE.sub(" ", value)
    decoded = unescape(without_tags)
    return _SPACE_RE.sub(" ", decoded).strip()


def _clip(value: str, limit: int) -> str:
    cleaned = _clean_text(value)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def _source_label(item: ContentItem) -> str:
    metadata = item.metadata
    for key in ("feed_name", "source_name", "channel", "subreddit", "repo", "watchlist"):
        value = metadata.get(key)
        if value:
            if key == "channel":
                return f"@{value}"
            if key == "subreddit":
                return f"r/{value}"
            return str(value)

    host = urlparse(str(item.url)).hostname
    if host:
        return host.removeprefix("www.")
    return item.author or item.source_type.value


def _category_label(item: ContentItem) -> str:
    category = item.metadata.get("category")
    if not category:
        return ""
    return _localized_label(str(category))


def _tags(item: ContentItem) -> list[str]:
    raw_tags: Iterable[object] = item.ai_tags or item.metadata.get("tags") or []
    tags: list[str] = []
    for raw_tag in raw_tags:
        tag = _localized_label(_clean_text(str(raw_tag)))
        if tag and tag not in tags:
            tags.append(tag)
        if len(tags) == 5:
            break
    return tags


def _localized_label(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    labels = {
        "ai": "AI",
        "ml": "机器学习",
        "x": "X",
        "rss": "RSS",
        "x-rss": "X 订阅",
        "x-ai-dev": "AI 开发",
        "x-product-growth": "产品增长",
        "x-crawler": "抓取工具",
        "x-design": "设计",
        "x-media": "媒体",
        "crawler": "抓取",
        "scraper": "抓取",
        "scraping": "抓取",
        "github": "GitHub",
        "hackernews": "技术社区",
        "finance": "金融",
        "startup": "创业",
        "product": "产品",
        "growth": "增长",
        "research": "研究",
        "security": "安全",
        "tool": "工具",
        "tools": "工具",
        "open-source": "开源",
        "opensource": "开源",
    }
    if normalized in labels:
        return labels[normalized]
    if _has_cjk(value):
        return value
    return value.replace("-", " ").title()
