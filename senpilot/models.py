from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
import json

CATEGORIES = ("Exhibits", "Key Documents", "Other Documents", "Transcripts", "Recordings")


class RetrievalError(RuntimeError):
    """A request cannot safely continue with the current website state."""


class MatterNotFound(RetrievalError):
    pass


class DownloadError(RuntimeError):
    """An individual file failed, after returning the browser to its list."""


class SiteAccessBlocked(RetrievalError):
    """The website asked the agent to stop or requires human interaction."""


@dataclass(frozen=True)
class Document:
    category: str
    position: int
    source_id: str | None
    title: str
    date: str | None
    security: str | None
    extension: str | None
    raw_fields: dict[str, str]
    occurrence: int = 1

    @property
    def fingerprint(self) -> str:
        identity = [self.category, self.source_id, self.title, self.date, self.security, self.extension]
        return sha256(json.dumps(identity, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]

    @property
    def key(self) -> str:
        return f"{self.fingerprint}_{self.occurrence}"

    @property
    def available(self) -> bool:
        return (self.security or "").casefold() == "public" or (
            self.category == "Recordings" and self.security is None)


def selection_order(documents: list[Document]) -> list[Document]:
    """Newest dates first, with deterministic identifiers and titles for ties."""
    def key(document):
        date = datetime.strptime(document.date, "%m/%d/%Y").toordinal() if document.date else 0
        return (-date, (document.source_id or document.title).casefold(), document.occurrence, document.key)

    return sorted(documents, key=key)


def identify_occurrences(documents: list[Document]) -> list[Document]:
    """Keep identical source labels as separate entries within the captured list."""
    counts = {}
    identified = []
    for document in sorted(documents, key=lambda doc: doc.position):
        fingerprint = document.fingerprint
        counts[fingerprint] = counts.get(fingerprint, 0) + 1
        identified.append(replace(document, occurrence=counts[fingerprint]))
    return identified
