"""Markdown / plain-text parser adapter (``parse.markdown``; ING-01 Markdown/TXT, incl. Obsidian notes).

Recognizes ATX headings, fenced code (with language), display math (``$$ … $$`` and ``\\[ … \\]``), lists, tables
and paragraphs. Obsidian ``[[wikilinks]]`` become plain text (``[[Page|Alias]]`` → ``Alias``). Plain text files are
split into paragraphs on blank lines.
"""

from __future__ import annotations

import re
from typing import Literal

from engine.ingest.normalized import Block, NormalizedDoc

ADAPTER_ID = "parse.markdown"
VERSION = "1"

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^(```|~~~)\s*([\w+#.-]*)\s*$")
_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_TABLE = re.compile(r"^\s*\|.*\|\s*$")
_WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]")
_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def _clean(text: str) -> str:
    return _WIKILINK.sub(lambda m: (m.group(2) or m.group(1)).strip(), text)


def parse_markdown(
    text: str, title: str | None = None, source_kind: Literal["markdown", "text"] = "markdown"
) -> NormalizedDoc:
    text = _FRONT_MATTER.sub("", text.replace("\r\n", "\n"))
    lines = text.split("\n")
    blocks: list[Block] = []
    para: list[str] = []
    list_buf: list[str] = []
    table_buf: list[str] = []

    def flush() -> None:
        if para:
            blocks.append(Block(kind="paragraph", text=_clean(" ".join(p.strip() for p in para))))
            para.clear()
        if list_buf:
            blocks.append(Block(kind="list", text=_clean("\n".join(list_buf))))
            list_buf.clear()
        if table_buf:
            blocks.append(Block(kind="table", text="\n".join(table_buf)))
            table_buf.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        fence = _FENCE.match(line)
        if fence:
            flush()
            marker, lang = fence.group(1), fence.group(2) or None
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith(marker):
                body.append(lines[i])
                i += 1
            blocks.append(Block(kind="code", text="\n".join(body), language=lang))
            i += 1
            continue
        stripped = line.strip()
        if stripped.startswith(("$$", "\\[")):
            flush()
            closer = "$$" if stripped.startswith("$$") else "\\]"
            body_text = stripped[2:]
            if body_text.endswith(closer) and len(body_text) >= len(closer):
                math = body_text[: -len(closer)]
            else:
                parts = [body_text]
                i += 1
                while i < len(lines) and closer not in lines[i]:
                    parts.append(lines[i])
                    i += 1
                if i < len(lines):
                    parts.append(lines[i].split(closer)[0])
                math = "\n".join(parts)
            blocks.append(Block(kind="math", text=math.strip()))
            i += 1
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            blocks.append(Block(kind="heading", text=_clean(heading.group(2)), level=len(heading.group(1))))
        elif not stripped:
            flush()
        elif _TABLE.match(line):
            if para or list_buf:
                flush()
            table_buf.append(stripped)
        elif _LIST.match(line) or (list_buf and line.startswith(("  ", "\t"))):
            if para or table_buf:
                flush()
            list_buf.append(line.rstrip())
        else:
            if list_buf or table_buf:
                flush()
            para.append(line)
        i += 1
    flush()
    return NormalizedDoc(
        source_kind=source_kind,
        title=title,
        blocks=tuple(blocks),
        parser=ADAPTER_ID,
        parser_version=VERSION,
    )


def parse_text(text: str, title: str | None = None) -> NormalizedDoc:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.replace("\r\n", "\n")) if p.strip()]
    blocks = tuple(Block(kind="paragraph", text=" ".join(p.split())) for p in paragraphs)
    return NormalizedDoc(source_kind="text", title=title, blocks=blocks, parser=ADAPTER_ID, parser_version=VERSION)
