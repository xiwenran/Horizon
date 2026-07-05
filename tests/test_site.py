from datetime import datetime, timezone

from src.models import ContentItem, SourceType
from src.services.site import LocalSiteGenerator


def make_item(
    item_id: str,
    *,
    title: str,
    score: float,
    published_at: datetime,
    category: str = "x-rss",
) -> ContentItem:
    return ContentItem(
        id=item_id,
        source_type=SourceType.RSS,
        title=title,
        url=f"https://example.com/{item_id}",
        content="<p>raw content with <strong>markup</strong></p>",
        author="Example",
        published_at=published_at,
        metadata={
            "feed_name": "GitTrend0x",
            "category": category,
            "tags": ["crawler"],
            "title_zh": f"{title} 中文标题",
            "detailed_summary_zh": f"{title} 的中文摘要",
        },
        ai_score=score,
        ai_reason="值得看，因为它补充了抓取和限流相关线索。",
        ai_summary=f"{title} 的中文摘要",
        ai_tags=["X", "RSS"],
        personal_score=8.8,
        personal_reason_zh="优化信息源筛选策略。",
        suggested_action_zh="加入下一轮抓取策略复盘。",
    )


def test_local_site_generator_writes_index(tmp_path) -> None:
    generator = LocalSiteGenerator(tmp_path)
    output = generator.write(
        [
            make_item(
                "lower",
                title="Lower score",
                score=7.4,
                published_at=datetime(2026, 7, 4, 8, 0, tzinfo=timezone.utc),
                category="x-design",
            ),
            make_item(
                "higher",
                title="Higher score",
                score=9.2,
                published_at=datetime(2026, 7, 4, 9, 0, tzinfo=timezone.utc),
            ),
        ],
        date="2026-07-04",
        total_items=12,
        generated_at=datetime(2026, 7, 4, 10, 30, tzinfo=timezone.utc),
    )

    html = output.read_text(encoding="utf-8")

    assert output == tmp_path / "index.html"
    assert "<title>2026.07.04 信息简报</title>" in html
    assert "2026.07.04 信息简报" in html
    assert '<p class="brand">' not in html
    assert "从订阅源里挑出值得看的更新" not in html
    assert "2 / 12" in html
    assert html.index("Higher score 中文标题") < html.index("Lower score 中文标题")
    assert "GitTrend0x" in html
    assert "https://example.com/higher" in html
    assert "X 订阅" in html
    assert "设计" in html
    assert "X Design" not in html
    assert "评分 9.2" in html
    assert "backdrop-filter: blur(24px)" in html
    assert "translateY(-7px)" in html
    assert "cardIn 700ms" in html
    assert "价值点" in html
    assert "匹配 8.8" not in html
    assert html.index("Higher score 中文标题") < html.index("价值点") < html.index("Higher score 的中文摘要")
    assert "抓取" in html


def test_local_site_generator_escapes_html(tmp_path) -> None:
    generator = LocalSiteGenerator(tmp_path)
    output = generator.write(
        [
            make_item(
                "danger",
                title="<script>alert('x')</script>",
                score=8.8,
                published_at=datetime(2026, 7, 4, 9, 0, tzinfo=timezone.utc),
            )
        ],
        date="2026-07-04",
        total_items=1,
        generated_at=datetime(2026, 7, 4, 10, 30, tzinfo=timezone.utc),
    )

    html = output.read_text(encoding="utf-8")

    assert "<script>alert" not in html
    assert "alert(&#x27;x&#x27;) 中文标题" in html
