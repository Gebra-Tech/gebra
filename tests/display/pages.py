"""Reading the HTML wrapper back — the test-side half of REL-05's byte-exact recovery claim.

``gebra.display.render_html`` embeds the Mermaid text as a JSON string literal inside a
``<script type="application/json" id="diagram">`` element. A reader that wants the text back
parses the document and ``json.loads`` that element's content, which is what the display and
CLI suites do here — through the standard library's ``html.parser``, so "the document parses"
and "the text is recoverable" are one observation. Pure text handling: nothing here imports
langgraph, executes anything, or opens a socket (WA-07).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from html.parser import HTMLParser

__all__ = ["PageShape", "embedded_mermaid", "read_page"]

#: The ``id`` of the JSON script element the wrapper embeds the text in.
DIAGRAM_ELEMENT_ID = "diagram"


@dataclass
class PageShape:
    """What a walk over the wrapper page found.

    Attributes:
        doctype: The document type declaration, ``"DOCTYPE html"`` for an HTML5 page.
        title: The ``<title>`` text.
        heading: The ``<h1>`` text.
        scripts: Every ``<script>`` element's attributes, in document order.
        json_body: The content of the JSON script element, verbatim (not yet decoded).
        module_body: The content of the ``<script type="module">`` element, verbatim.
        noscript_pre: The ``<pre>`` text inside ``<noscript>``, entities decoded.
        style: The ``<style>`` block's text.
    """

    doctype: str | None = None
    title: str = ""
    heading: str = ""
    scripts: list[dict[str, str | None]] = field(default_factory=list)
    json_body: str = ""
    module_body: str = ""
    noscript_pre: str = ""
    style: str = ""

    @property
    def embedded_text(self) -> str:
        """The Mermaid text, decoded from the JSON script element."""
        decoded = json.loads(self.json_body)
        assert isinstance(decoded, str), "the diagram element does not carry a JSON string"
        return decoded


class _Walker(HTMLParser):
    """A stack-tracking walk that files each element's text under the field it belongs to."""

    def __init__(self) -> None:
        super().__init__()
        self.shape = PageShape()
        self._stack: list[tuple[str, dict[str, str | None]]] = []

    def handle_decl(self, decl: str) -> None:
        self.shape.doctype = decl

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        self._stack.append((tag, attributes))
        if tag == "script":
            self.shape.scripts.append(attributes)

    def handle_endtag(self, tag: str) -> None:
        while self._stack:
            popped, _ = self._stack.pop()
            if popped == tag:
                break

    def handle_data(self, data: str) -> None:
        if not self._stack:
            return
        tag, attributes = self._stack[-1]
        if tag == "title":
            self.shape.title += data
        elif tag == "h1":
            self.shape.heading += data
        elif tag == "style":
            self.shape.style += data
        elif tag == "script" and attributes.get("id") == DIAGRAM_ELEMENT_ID:
            self.shape.json_body += data
        elif tag == "script" and attributes.get("type") == "module":
            self.shape.module_body += data
        elif tag == "pre" and any(open_tag == "noscript" for open_tag, _ in self._stack):
            self.shape.noscript_pre += data


def read_page(document: str) -> PageShape:
    """Parse ``document`` with ``html.parser`` and return what the walk found."""
    walker = _Walker()
    walker.feed(document)
    walker.close()
    return walker.shape


def embedded_mermaid(document: str) -> str:
    """The Mermaid text the wrapper embeds, recovered byte for byte from the JSON element."""
    return read_page(document).embedded_text
