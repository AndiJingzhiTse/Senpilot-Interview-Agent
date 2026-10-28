"""Read FileMaker's virtual list through its rendered DOM and scrollbar."""

import re

from playwright.sync_api import Page, TimeoutError, expect

from .browser import wait_for_ui
from .models import Document, RetrievalError, identify_occurrences

ROWS = ".v-grid-body > tr.v-grid-row"
SCROLLER = ".v-grid-scroller-vertical"
READ_ROWS = """nodes => nodes.flatMap((row, dom_index) => {
  const fields = {};
  for (const field of row.querySelectorAll('.fm-textarea[id]')) {
    const match = field.id.match(/^b0p1o(\\d+)i\\d+i0r(\\d+)$/);
    if (match) fields[match[1] + '.' + match[2]] = field.innerText.trim();
  }
  if (Object.keys(fields).length < 3 || !row.innerText.includes('GO GET IT')) return [];
  const height = row.getBoundingClientRect().height;
  return [{dom_index, position: Math.round(new DOMMatrix(row.style.transform).m42 / height), fields}];
})"""
WAIT_POSITION = """position => Array.from(document.querySelectorAll('.v-grid-body > tr.v-grid-row')).some(row => {
  const height = row.getBoundingClientRect().height;
  return height && Math.round(new DOMMatrix(row.style.transform).m42 / height) === position
    && row.querySelectorAll('.fm-textarea[id]').length >= 3 && row.innerText.includes('GO GET IT');
})"""
WAIT_DOCUMENT = """expected => Array.from(document.querySelectorAll('.v-grid-body > tr.v-grid-row')).some(row => {
  const height = row.getBoundingClientRect().height;
  if (!height || Math.round(new DOMMatrix(row.style.transform).m42 / height) !== expected.position) return false;
  const fields = {};
  for (const field of row.querySelectorAll('.fm-textarea[id]')) {
    const match = field.id.match(/^b0p1o(\\d+)i\\d+i0r(\\d+)$/);
    if (match) fields[match[1] + '.' + match[2]] = field.innerText.trim();
  }
  return Object.entries(expected.fields).every(([key,value]) => fields[key] === value);
})"""


def parse_row(category: str, raw: dict) -> Document:
    fields = raw["fields"]
    source_field = {"Other Documents": "201.1", "Key Documents": "268.1", "Exhibits": "300.1"}
    source_id = fields.get(source_field.get(category, "")) or None
    if category in source_field and not source_id:
        raise RetrievalError("A populated row is missing its source identifier")
    date_field = "201.1" if category in {"Transcripts", "Recordings"} else "203.1"
    parts = [fields[key] for key in sorted(fields) if key.startswith("202.") and fields[key]]
    extension_field = {"Other Documents": "308.1", "Key Documents": "284.1", "Exhibits": "314.1"}
    extension = fields.get(extension_field.get(category, "")) or None
    if category == "Transcripts":
        formats = {"pdf", "doc", "docx", "xls", "xlsx"}
        extension = next(("." + part.casefold() for part in parts if part.casefold() in formats), None)
        parts = [part for part in parts if part.casefold() not in formats]
    title = " ".join(parts)
    if not title and not source_id:
        raise RetrievalError("A source row has no usable document identity")
    return Document(category, raw["position"], source_id, title,
                    fields.get(date_field) or None, fields.get("204.1") or None,
                    extension.casefold() if extension else None, fields)


def scroll_to(page: Page, position: int, row_height: float) -> None:
    metrics = page.locator(SCROLLER).evaluate("n=>({height:n.clientHeight,total:n.scrollHeight})")
    if metrics["total"] > metrics["height"] > 0:
        top = min(position * row_height, metrics["total"] - metrics["height"])
        page.locator(SCROLLER).evaluate("(n,top)=>{n.scrollTop=top}", top)
        first = int(top // row_height)
    else:
        first = 0
    page.wait_for_function(WAIT_POSITION, arg=first, polling=100)
    wait_for_ui(page)


def read_catalog(page: Page, category: str, expected_count: int) -> list[Document]:
    if expected_count == 0:
        return []
    page.get_by_role("button", name=re.compile(rf"^{re.escape(category)}\s*-\s*\d+$")).click()
    page.get_by_role("button", name="GO GET IT", exact=True).first.wait_for()
    wait_for_ui(page)
    height = page.locator(ROWS).first.evaluate("n=>n.getBoundingClientRect().height")
    view = page.locator(".v-grid-tablewrapper").evaluate("n=>n.clientHeight")
    step = max(1, int(view / height * 0.7))
    seen = {}
    for start in range(0, expected_count + step, step):
        scroll_to(page, start, height)
        for raw in page.locator(ROWS).evaluate_all(READ_ROWS):
            document = parse_row(category, raw)
            if not 0 <= document.position < expected_count:
                raise RetrievalError("The source list count changed during enumeration")
            previous = seen.get(document.position)
            if previous is not None and previous.key != document.key:
                raise RetrievalError("A source row changed while its catalog was being read")
            seen[document.position] = document
        if len(seen) == expected_count:
            documents = [seen[position] for position in range(expected_count)]
            return identify_occurrences(documents)
    raise RetrievalError(f"Only enumerated {len(seen)} of {expected_count} source rows")


def locate_document(page: Page, document: Document):
    height = page.locator(ROWS).first.evaluate("n=>n.getBoundingClientRect().height")
    scroll_to(page, document.position, height)
    try:
        page.wait_for_function(WAIT_DOCUMENT, arg={"position": document.position, "fields": document.raw_fields}, polling=100)
    except TimeoutError as error:
        failure = RetrievalError("The selected source row changed or did not finish updating")
        failure.details = {"expected_position": document.position, "expected_fields": document.raw_fields,
                           "observed_rows": page.locator(ROWS).evaluate_all(READ_ROWS)}
        raise failure from error
    for raw in page.locator(ROWS).evaluate_all(READ_ROWS):
        if raw["position"] == document.position:
            current = parse_row(document.category, raw)
            if current.fingerprint != document.fingerprint:
                raise RetrievalError("The selected row no longer matches its catalog identity")
            row = page.locator(ROWS).nth(raw["dom_index"])
            expect(row).to_be_visible()
            return row
    raise RetrievalError("The selected source row could not be found after scrolling")
