from datetime import datetime, timezone

from src.models import ContentItem, ObsidianExportConfig, SourceType
from src.services.obsidian_export import ObsidianExporter


def make_item(item_id: str, personal_score: float) -> ContentItem:
    return ContentItem(
        id=item_id,
        source_type=SourceType.RSS,
        title=f"{item_id} title",
        url=f"https://example.com/{item_id}",
        content="long raw content should not be exported in full",
        author="Example",
        published_at=datetime(2026, 7, 5, tzinfo=timezone.utc),
        ai_score=7.0,
        ai_summary=f"{item_id} 摘要内容，应该被压缩到较短长度。",
        ai_tags=["AI 工具", "抓取"],
        personal_score=personal_score,
        personal_reason_zh=f"{item_id} 与 Horizon 雷达直接相关。",
    )


def test_obsidian_export_writes_only_high_personal_score(tmp_path) -> None:
    config = ObsidianExportConfig(
        enabled=True,
        vault_path=str(tmp_path),
        relative_dir="决策/行业动态/Horizon信息雷达",
        personal_score_threshold=8.5,
    )
    output = ObsidianExporter(config).write(
        [make_item("high", 8.5), make_item("low", 8.49)],
        date="2026-07-05",
    )

    assert output == tmp_path / "决策/行业动态/Horizon信息雷达/2026-07-05.md"
    text = output.read_text(encoding="utf-8")
    assert "high title" in text
    assert "low title" not in text
    assert "个人相关分 8.5 分以上" in text
    assert "价值点：" in text
    assert "https://example.com/high" in text
    assert "long raw content should not be exported in full" not in text


def test_obsidian_export_noops_without_matching_items(tmp_path) -> None:
    config = ObsidianExportConfig(enabled=True, vault_path=str(tmp_path))

    output = ObsidianExporter(config).write([make_item("low", 7.0)], date="2026-07-05")

    assert output is None
