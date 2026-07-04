"""Allowlist HTML sanitizer for user-authored rich text (comments, notes).

Comment bodies are rich HTML rendered into other users' browsers, so this is a
stored-XSS surface. We keep only a safe allowlist of tags/attributes and drop
everything else (scripts, event handlers, javascript: URLs, styles). Built on the
stdlib HTMLParser so there is no extra dependency to install.
"""

from html import escape
from html.parser import HTMLParser

_ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "s", "strike", "del",
    "a", "ul", "ol", "li", "br", "p", "h3", "blockquote", "pre", "code", "span", "div", "img",
}
_VOID_TAGS = {"br", "img"}
_DROP_CONTENT_TAGS = {"script", "style"}
_ALLOWED_ATTRS = {
    "a": {"href", "title"},
    "span": {"class"},
    "img": {"src", "alt"},
}
_SAFE_URL_PREFIXES = ("http://", "https://", "mailto:", "/", "#")


def _safe_url(value: str, allow_data_image: bool = False) -> bool:
    v = (value or "").strip().lower()
    if allow_data_image and v.startswith("data:image/"):
        return True
    return v.startswith(_SAFE_URL_PREFIXES)


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0  # inside script/style

    def _emit_open(self, tag: str, attrs, self_closing: bool) -> None:
        allowed = {a.lower() for a in _ALLOWED_ATTRS.get(tag, set())}
        kept = []
        for name, value in attrs:
            name = name.lower()
            if name not in allowed or value is None:
                continue
            if name in ("href", "src"):
                if not _safe_url(value, allow_data_image=(tag == "img" and name == "src")):
                    continue
            kept.append(f'{name}="{escape(value, quote=True)}"')
        attr_str = (" " + " ".join(kept)) if kept else ""
        if tag in _VOID_TAGS:
            self.parts.append(f"<{tag}{attr_str}>")
        elif self_closing:
            self.parts.append(f"<{tag}{attr_str}></{tag}>")
        else:
            self.parts.append(f"<{tag}{attr_str}>")

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _DROP_CONTENT_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth or tag not in _ALLOWED_TAGS:
            return
        self._emit_open(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if self._skip_depth or tag in _DROP_CONTENT_TAGS or tag not in _ALLOWED_TAGS:
            return
        self._emit_open(tag, attrs, self_closing=True)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _DROP_CONTENT_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth or tag not in _ALLOWED_TAGS or tag in _VOID_TAGS:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if self._skip_depth:
            return
        self.parts.append(escape(data))


def clean_html(html: str | None) -> str:
    """Return a sanitized copy of the given HTML, safe to store and render."""
    if not html:
        return ""
    parser = _Sanitizer()
    parser.feed(html)
    parser.close()
    return "".join(parser.parts).strip()
