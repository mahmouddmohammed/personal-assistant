"""arXiv Atom API. stdlib XML parsing to keep deps light."""
import xml.etree.ElementTree as ET

import requests

_NS = {"a": "http://www.w3.org/2005/Atom"}


def search_arxiv(query: str, max_results: int = 5) -> list[dict]:
    resp = requests.get(
        "http://export.arxiv.org/api/query",
        params={"search_query": f"all:{query}", "max_results": max_results},
        timeout=10,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    papers = []
    for entry in root.findall("a:entry", _NS):
        papers.append({
            "title": (entry.findtext("a:title", default="", namespaces=_NS) or "").strip(),
            "authors": [a.findtext("a:name", default="", namespaces=_NS) for a in entry.findall("a:author", _NS)],
            "url": entry.findtext("a:id", default="", namespaces=_NS).strip(),
            "published": entry.findtext("a:published", default=None, namespaces=_NS),
            "abstract": (entry.findtext("a:summary", default="", namespaces=_NS) or "").strip(),
        })
    return papers
