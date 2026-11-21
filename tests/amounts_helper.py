"""Test helper: a signed-in page with its amounts filled in from /api/amounts, as amounts.js does."""

from __future__ import annotations

import json
import re
from html import escape
from urllib.parse import quote


def amounts_for(client, url: str) -> dict:
    r = client.get("/api/amounts?path=" + quote(url, safe=""))
    assert r.status_code == 200, r.text
    return r.json()["v"]


def fill(html: str, values: dict) -> str:
    def text(m):
        v = values.get(m.group(1))
        return escape(v, quote=False) if isinstance(v, str) else "—"

    def attrs(m):
        out = []
        for pair in m.group(1).split(" "):
            name, key = pair.split("=", 1)
            v = values.get(key)
            if v is None:
                continue
            v = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
            out.append(f' {name}="{escape(v)}"')
        return "".join(out)

    def js(m):
        v = values.get(m.group(2))
        return m.group(1) + (json.dumps(v, ensure_ascii=False) if v is not None else "null") + "</script>"

    html = re.sub(r'<span data-amt="([^"]*)"></span>', text, html)
    html = re.sub(r' data-amt-attr="([^"]*)"', attrs, html)
    html = re.sub(r'(<script [^>]*data-amt-json="([^"]*)"[^>]*>)null</script>', js, html)
    return html


def with_amounts(client, url: str) -> str:
    """The page as the browser shows it once amounts.js has filled it in."""
    return fill(client.get(url).text, amounts_for(client, url))
