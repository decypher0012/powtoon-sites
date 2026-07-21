from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Bookmark:
    name: str
    url: str


class _BookmarkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.url: str | None = None
        self.text: list[str] = []
        self.bookmarks: list[Bookmark] = []

    def handle_starttag(self, tag, attrs):
        if tag.casefold() == "a":
            self.url = dict(attrs).get("href")
            self.text = []

    def handle_data(self, data):
        if self.url is not None:
            self.text.append(data)

    def handle_endtag(self, tag):
        if tag.casefold() != "a" or self.url is None:
            return
        parsed = urlparse(self.url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            name = "".join(self.text).strip() or parsed.netloc
            self.bookmarks.append(Bookmark(name, self.url))
        self.url = None
        self.text = []


def parse_bookmarks(path: Path) -> list[Bookmark]:
    parser = _BookmarkParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    seen: set[str] = set()
    result = []
    for item in parser.bookmarks:
        key = item.url.casefold()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
