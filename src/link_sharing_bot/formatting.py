"""Safe small-caps and custom markup renderer.

Supported syntax: (B)...(/B), (I), (U), (S), (CODE), (PRE), (Q),
(SPOILER), and (LINK url="https://...")...(/LINK).
"""
from __future__ import annotations
import html
import re
from urllib.parse import urlparse

SMALL_CAPS = str.maketrans({
    "a":"ᴀ", "b":"ʙ", "c":"ᴄ", "d":"ᴅ", "e":"ᴇ", "f":"ꜰ", "g":"ɢ",
    "h":"ʜ", "i":"ɪ", "j":"ᴊ", "k":"ᴋ", "l":"ʟ", "m":"ᴍ", "n":"ɴ",
    "o":"ᴏ", "p":"ᴘ", "q":"ǫ", "r":"ʀ", "s":"ѕ", "t":"ᴛ", "u":"ᴜ",
    "v":"ᴠ", "w":"ᴡ", "x":"x", "y":"ʏ", "z":"ᴢ",
    "A":"ᴀ", "B":"ʙ", "C":"ᴄ", "D":"ᴅ", "E":"ᴇ", "F":"ꜰ", "G":"ɢ",
    "H":"ʜ", "I":"ɪ", "J":"ᴊ", "K":"ᴋ", "L":"ʟ", "M":"ᴍ", "N":"ɴ",
    "O":"ᴏ", "P":"ᴘ", "Q":"ǫ", "R":"ʀ", "S":"ѕ", "T":"ᴛ", "U":"ᴜ",
    "V":"ᴠ", "W":"ᴡ", "X":"x", "Y":"ʏ", "Z":"ᴢ",
})
TOKEN = re.compile(r'\((?P<close>/)?(?P<tag>B|I|U|S|CODE|PRE|Q|SPOILER|LINK)(?:\s+url="(?P<url>[^"]+)")?\)', re.I)
TAG_MAP = {"B": "b", "I": "i", "U": "u", "S": "s", "CODE": "code", "PRE": "pre", "Q": "blockquote", "SPOILER": "tg-spoiler"}


def _small(text: str) -> str:
    return text.translate(SMALL_CAPS)


def render_text(source: str, small_caps: bool = True) -> str:
    """Convert the user's light markup to Telegram HTML with escaped text."""
    if source is None:
        source = ""
    # Convenience Markdown aliases used in default templates.
    source = re.sub(r"\*\*(.+?)\*\*", r"(B)\1(/B)", source, flags=re.S)
    source = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"(I)\1(/I)", source)
    source = re.sub(r"`([^`\n]+)`", r"(CODE)\1(/CODE)", source)
    out: list[str] = []
    stack: list[tuple[str, str]] = []
    pos = 0
    for match in TOKEN.finditer(source):
        segment = source[pos:match.start()]
        in_code = any(tag in {"CODE", "PRE"} for tag, _ in stack)
        if small_caps and not in_code:
            segment = _small(segment)
        out.append(html.escape(segment))
        tag = match.group("tag").upper()
        is_close = bool(match.group("close"))
        if tag == "LINK":
            if is_close:
                if stack and stack[-1][0] == "LINK":
                    out.append("</a>")
                    stack.pop()
                else:
                    out.append(html.escape(match.group(0)))
            else:
                url = match.group("url") or ""
                parsed = urlparse(url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    out.append(html.escape(match.group(0)))
                else:
                    out.append(f'<a href="{html.escape(url, quote=True)}">')
                    stack.append(("LINK", "a"))
        elif tag in TAG_MAP:
            html_tag = TAG_MAP[tag]
            if is_close:
                if stack and stack[-1][0] == tag:
                    out.append(f"</{html_tag}>")
                    stack.pop()
                else:
                    out.append(html.escape(match.group(0)))
            else:
                out.append(f"<{html_tag}>")
                stack.append((tag, html_tag))
        pos = match.end()
    segment = source[pos:]
    in_code = any(tag in {"CODE", "PRE"} for tag, _ in stack)
    out.append(html.escape(_small(segment) if small_caps and not in_code else segment))
    # Close any valid open tags to avoid malformed Telegram HTML.
    while stack:
        _tag, html_tag = stack.pop()
        out.append(f"</{html_tag}>")
    return "".join(out)


def caption_chunks(source: str, small_caps: bool = True, limit: int = 900) -> list[str]:
    """Split long raw text into safe-ish caption chunks at paragraph/word boundaries."""
    if len(source) <= limit:
        return [render_text(source, small_caps)]
    chunks: list[str] = []
    remaining = source
    while remaining:
        if len(remaining) <= limit:
            part, remaining = remaining, ""
        else:
            cut = remaining.rfind("\n", 0, limit)
            if cut < limit // 2:
                cut = remaining.rfind(" ", 0, limit)
            if cut < limit // 2:
                cut = limit
            part, remaining = remaining[:cut], remaining[cut:].lstrip()
        chunks.append(render_text(part, small_caps))
    return chunks
