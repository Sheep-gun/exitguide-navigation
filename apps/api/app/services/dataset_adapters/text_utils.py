from __future__ import annotations

import re
from html.parser import HTMLParser

from app.services.dataset_adapters.common import normalize_text


BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "div",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "nav",
    "p",
    "section",
    "table",
    "td",
    "th",
    "tr",
}
SKIP_TAGS = {"script", "style", "noscript", "svg"}


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        elif tag in BLOCK_TAGS and not self.skip_depth:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif tag in BLOCK_TAGS and not self.skip_depth:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)


def html_to_text(value: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(value)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n(?:\s*\n)+", "\n\n", text)
    return normalize_text(text)


def decode_bytes(payload: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "utf-8", "cp949", "cp1252"):
        try:
            return payload.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", errors="replace"), "utf-8-replacement"


def nullable(value: str | None) -> str:
    return "" if value is None or value.strip().upper() == "NULL" else value.strip()


def infer_document_type(name: str, url: str = "") -> str:
    probe = f"{name} {url}".lower()
    if "privacy" in probe or "개인정보" in probe:
        return "privacy_policy"
    if "cookie" in probe or "tracker" in probe:
        return "trackers_policy"
    return "terms_of_service"
