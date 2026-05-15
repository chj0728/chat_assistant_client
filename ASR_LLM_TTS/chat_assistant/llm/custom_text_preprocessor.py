import re
from typing import Any

INTENT_TAG_START = "<INTENT>"
INTENT_TAG_END = "</INTENT>"
INTENT_TAG_PATTERN = re.compile(
    rf"{re.escape(INTENT_TAG_START)}.*?{re.escape(INTENT_TAG_END)}", re.DOTALL
)


def normalize_message_content(content: Any) -> str:
    """将 LangChain 消息内容统一转换为字符串。"""
    if isinstance(content, list):
        return "".join(part if isinstance(part, str) else str(part) for part in content)
    if content is None:
        return ""
    return str(content)


def find_protected_suffix_start(buffer: str) -> int | None:
    """返回尾部未闭合 INTENT 标签的起始位置；若不存在则返回 None。"""
    last_open = buffer.rfind(INTENT_TAG_START)
    if last_open < 0:
        return None

    last_close = buffer.rfind(INTENT_TAG_END)
    if last_close > last_open:
        return None

    return last_open


def find_trailing_intent_tag_start(buffer: str) -> int | None:
    """返回尾部完整或未闭合 INTENT 标签的起始位置；若尾部不存在则返回 None。"""
    last_open = buffer.rfind(INTENT_TAG_START)
    if last_open < 0:
        return None

    last_close = buffer.rfind(INTENT_TAG_END)
    if last_close < last_open:
        return last_open

    trailing_intent_end = last_close + len(INTENT_TAG_END)
    if trailing_intent_end == len(buffer):
        return last_open

    return None


def find_trailing_intent_prefix_start(buffer: str) -> int | None:
    """返回尾部未拼完整的 INTENT 起始标签前缀位置；若不存在则返回 None。"""
    for prefix_len in range(len(INTENT_TAG_START) - 1, 0, -1):
        prefix = INTENT_TAG_START[:prefix_len]
        if buffer.endswith(prefix):
            return len(buffer) - prefix_len
    return None


def find_trailing_protected_suffix_start(buffer: str) -> int | None:
    """返回尾部受保护后缀的起始位置，覆盖完整、未闭合及部分 INTENT 标签。"""
    trailing_intent_tag_start = find_trailing_intent_tag_start(buffer)
    if trailing_intent_tag_start is not None:
        return trailing_intent_tag_start
    return find_trailing_intent_prefix_start(buffer)


def build_visible_text_and_raw_offsets(buffer: str) -> tuple[str, list[int]]:
    """构造忽略完整 INTENT 标签后的可见文本，以及可见字符到原始下标的映射。"""
    visible_parts: list[str] = []
    raw_offsets: list[int] = []
    cursor = 0

    for match in INTENT_TAG_PATTERN.finditer(buffer):
        segment = buffer[cursor : match.start()]
        visible_parts.append(segment)
        raw_offsets.extend(range(cursor + 1, match.start() + 1))
        cursor = match.end()

    tail_segment = buffer[cursor:]
    visible_parts.append(tail_segment)
    raw_offsets.extend(range(cursor + 1, len(buffer) + 1))

    return "".join(visible_parts), raw_offsets


def split_trailing_protected_suffix(buffer: str) -> tuple[str, str]:
    """拆分正文与尾部受保护的 INTENT 标签后缀。"""
    protected_suffix_start = find_trailing_protected_suffix_start(buffer)
    if protected_suffix_start is None:
        return buffer, ""
    return buffer[:protected_suffix_start], buffer[protected_suffix_start:]


def split_leading_intent_tags(buffer: str) -> tuple[list[str], str]:
    """拆分位于缓冲区开头的完整 INTENT 标签，保持标签整体输出。"""
    leading_tags: list[str] = []
    remaining = buffer

    while True:
        match = INTENT_TAG_PATTERN.match(remaining)
        if match is None:
            break
        leading_tags.append(match.group(0))
        remaining = remaining[match.end() :]

    return leading_tags, remaining


def select_stream_flush_index(
    buffer: str,
    *,
    min_chunk_chars: int,
    max_chunk_chars: int,
    punctuation_marks: str,
) -> int | None:
    """选择流式文本的切分位置，在指定窗口内优先按标点切分。"""
    protected_suffix_start = find_trailing_protected_suffix_start(buffer)
    searchable_buffer = (
        buffer[:protected_suffix_start]
        if protected_suffix_start is not None
        else buffer
    )
    searchable_text, raw_offsets = build_visible_text_and_raw_offsets(searchable_buffer)

    if len(searchable_text) < min_chunk_chars:
        return None

    window_end = min(len(searchable_text), max_chunk_chars)
    window_text = searchable_text[:window_end]
    window_start = min_chunk_chars - 1

    flush_index = None
    last_punctuation = max(
        (window_text.rfind(mark, window_start) for mark in punctuation_marks),
        default=-1,
    )
    if last_punctuation >= window_start:
        flush_index = raw_offsets[last_punctuation]
    elif len(searchable_text) >= max_chunk_chars:
        flush_index = raw_offsets[max_chunk_chars - 1]

    if flush_index is None:
        return None

    protected_suffix_start = find_protected_suffix_start(buffer)
    if protected_suffix_start is None or flush_index <= protected_suffix_start:
        return flush_index

    if protected_suffix_start >= min_chunk_chars:
        return protected_suffix_start

    return None
