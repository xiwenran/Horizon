from types import SimpleNamespace

from src.ai.client import AnthropicClient


def test_extract_text_content_skips_thinking_blocks() -> None:
    message = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="internal"),
            SimpleNamespace(type="text", text='{"ok": true}'),
        ]
    )

    assert AnthropicClient._extract_text_content(message) == '{"ok": true}'


def test_extract_text_content_joins_multiple_text_blocks() -> None:
    message = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text='{"a": 1,'),
            SimpleNamespace(type="thinking", thinking="internal"),
            SimpleNamespace(type="text", text='"b": 2}'),
        ]
    )

    assert AnthropicClient._extract_text_content(message) == '{"a": 1,\n"b": 2}'
