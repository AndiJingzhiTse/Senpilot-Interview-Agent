import re

from playwright.sync_api import Page, expect

from .models import CATEGORIES, MatterNotFound, RetrievalError

SITE = "https://uarb.novascotia.ca/fmi/webd/UARB15"
UI_TIMEOUT = 30000
OVERVIEW_FIELDS = {
    "matter_number": 286, "title": 290, "status": 289, "type": 298,
    "category": 287, "outcome": 295,
}


def wait_for_ui(page: Page) -> None:
    """Use Vaadin's testability hook to wait for queued UI updates to finish."""
    page.wait_for_function("""() => {
      const clients = window.vaadin && window.vaadin.clients;
      return clients && Object.keys(clients).length > 0 && Object.values(clients).every(
        client => typeof client.isActive === 'function' && !client.isActive());
    }""", polling=100)


def open_matter(page: Page, matter: str) -> dict[str, int]:
    """Activate and commit FileMaker's editor, then verify the actual result."""
    if re.fullmatch(r"M\d{5}", matter) is None:
        raise ValueError("Matter number must be M followed by five digits")
    page.goto(SITE)
    field = page.get_by_text("eg M01234", exact=True).locator("..").locator(".text")
    field.click()
    expect(field).to_have_attribute("contenteditable", "true", timeout=UI_TIMEOUT)
    field.fill(matter)
    field.press("Tab")
    page.locator("#b0p0o258i0i0r1").click()
    missing = page.get_by_role("dialog", name="No Records Found", exact=True)
    overview = page.get_by_role("button", name=re.compile(r"^Exhibits\s*-\s*\d+$"))
    missing.or_(overview).wait_for(state="visible")
    wait_for_ui(page)
    if missing.is_visible():
        missing.get_by_role("button", name="OK", exact=True).click()
        raise MatterNotFound(f"No matter matched {matter}")
    actual = page.locator("#b0p0o286i0i0r1").inner_text().strip()
    if actual != matter:
        raise RetrievalError(f"Requested {matter}, but the site returned {actual!r}")
    counts = {}
    for label in page.get_by_role("button").all_text_contents():
        match = re.fullmatch(r"(.+?)\s*-\s*(\d+)", " ".join(label.split()))
        if match and match[1] in CATEGORIES:
            counts[match[1]] = int(match[2])
    if set(counts) != set(CATEGORIES):
        raise RetrievalError("The overview did not expose all five category counts")
    return counts


def matter_metadata(page: Page, matter: str) -> dict:
    counts = open_matter(page, matter)
    result = {
        name: page.locator(f"#b0p0o{field}i0i0r1").inner_text().strip() or None
        for name, field in OVERVIEW_FIELDS.items()
    }
    result["dates"] = {}
    for label_id, value_id in [(309, 292), (310, 294)]:
        label = page.locator(f"#b0p0o{label_id}i0i0r1").inner_text().strip()
        value = page.locator(f"#b0p0o{value_id}i0i0r1").inner_text().strip()
        result["dates"][label] = value or None
    result.update({"source_url": SITE, "source_layout": "matter_overview",
                   "category_counts": counts, "category_entry_total": sum(counts.values()),
                   "count_note": "Category entries can overlap; this is not a unique file count."})
    return result


def prepare_export(page: Page, row):
    """Prepare one file through the normal export UI, with a safe header filename."""
    row.get_by_role("button", name="GO GET IT", exact=True).click()
    prompt = page.get_by_role("dialog", name=re.compile(r"^(Download Files|Export Field to File)$"))
    expect(prompt).to_be_visible(timeout=UI_TIMEOUT)
    export_name = None
    if prompt.get_by_role("button", name="OK", exact=True).count():
        filename = prompt.get_by_role("textbox")
        original = filename.input_value()
        normalized = re.sub(r"[^A-Za-z0-9._-]", "_", original)
        if not normalized or normalized in {".", ".."}:
            raise RetrievalError("The export dialog did not provide a usable filename")
        filename.fill(normalized)
        export_name = {"original": original, "normalized": normalized}
        prompt.get_by_role("button", name="OK", exact=True).click()
    dialog = page.get_by_role("dialog", name="Download Files", exact=True)
    expect(dialog).to_be_visible(timeout=UI_TIMEOUT)
    button = dialog.locator(".fm-download-button")
    expect(button).to_have_count(1, timeout=UI_TIMEOUT)
    expect(button).to_be_enabled(timeout=UI_TIMEOUT)
    return dialog, button, export_name


def close_exports(page: Page) -> None:
    """Clear only the export dialogs observed on this site; reject unknown state."""
    actions = {"Download Files": "Close", "Export Field to File": "Cancel",
               "Continue or Cancel Script": "Cancel"}
    for _ in range(4):
        dialog = page.get_by_role("dialog")
        if dialog.count() == 0:
            return
        for name, action in actions.items():
            current = page.get_by_role("dialog", name=name, exact=True)
            if current.is_visible():
                current.get_by_role("button", name=action, exact=True).click()
                expect(current).not_to_be_visible(timeout=UI_TIMEOUT)
                break
        else:
            raise RetrievalError("An unexpected dialog prevents further retrieval")
    raise RetrievalError("Export dialogs did not close")
