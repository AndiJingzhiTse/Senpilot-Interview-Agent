"""Read email requests and construct deterministic replies from verified results."""

from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formatdate, make_msgid
from html.parser import HTMLParser
import re


class MessageError(ValueError):
    pass


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"p", "div", "br", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def mailbox(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", value):
        raise MessageError("A valid single mailbox address is required")
    return value


@dataclass(frozen=True)
class IncomingMessage:
    sender: str
    subject: str
    text: str
    message_id: str | None


def read_message(raw: bytes, agent_address: str) -> IncomingMessage:
    if len(raw) > 1024 * 1024:
        raise MessageError("Incoming message exceeds the 1 MB request limit")
    message = BytesParser(policy=policy.default).parsebytes(raw)
    if message.get_content_type() == "multipart/report" or message.get("Auto-Submitted", "no").lower() != "no":
        raise MessageError("Automatic messages and delivery reports are ignored")
    if message.get("Precedence", "").lower() in {"bulk", "list", "junk"} or message.get("List-Id"):
        raise MessageError("Mailing list and bulk messages are ignored")
    headers = message.get_all("From", [])
    addresses = headers[0].addresses if len(headers) == 1 and not headers[0].defects else []
    if len(addresses) != 1:
        raise MessageError("The request must have exactly one valid From address")
    sender = mailbox(addresses[0].addr_spec)
    if sender.casefold() == agent_address.casefold():
        raise MessageError("Messages from the agent itself are ignored")
    body = message.get_body(preferencelist=("plain", "html"))
    if body is None:
        raise MessageError("The request has no supported text body")
    try:
        text = body.get_content()
    except (LookupError, ValueError, UnicodeError) as error:
        raise MessageError("The request body has an unsupported text encoding") from error
    if not isinstance(text, str):
        raise MessageError("The request has no supported text body")
    if body.get_content_subtype() == "html":
        parser = HTMLText()
        parser.feed(text)
        text = "".join(parser.parts)
    # Exclude ordinary quoted replies so previous requests do not create ambiguity.
    text = re.split(r"(?m)^On .+wrote:\s*$|^-----Original Message-----\s*$", text, maxsplit=1)[0]
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))
    subject = str(message.get("Subject", ""))[:500]
    identifier = str(message.get("Message-ID", ""))
    identifier = identifier if re.fullmatch(r"<[^<>\s]{1,250}>", identifier) else None
    return IncomingMessage(sender, subject, subject + "\n" + text, identifier)


def reply_message(incoming: IncomingMessage, agent_address: str, text: str) -> EmailMessage:
    message = EmailMessage(policy=policy.SMTP)
    message["From"] = mailbox(agent_address)
    message["To"] = mailbox(incoming.sender)
    subject = re.sub(r"[\r\n]", " ", incoming.subject)[:500]
    message["Subject"] = subject if subject.casefold().startswith("re:") else "Re: " + subject
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=agent_address.split("@", 1)[1])
    message["Auto-Submitted"] = "auto-replied"
    if incoming.message_id:
        message["In-Reply-To"] = incoming.message_id
        message["References"] = incoming.message_id
    message.set_content(text)
    return message


def result_text(package: dict, attachment_state: str) -> str:
    manifest = package["manifest"]
    request, matter = manifest["request"], manifest.get("matter")
    lines = ["Hello,", ""]
    if matter:
        lines.extend([f"{request['matter']}: {matter.get('title') or 'Title not provided'}.",
                      f"Type: {matter.get('type') or 'Not provided'}. Category: {matter.get('category') or 'Not provided'}.",
                      f"Status: {matter.get('status') or 'Not provided'}. Outcome: {matter.get('outcome') or 'Not provided'}."])
        for label, value in matter.get("dates", {}).items():
            lines.append(f"{label}: {value or 'Not provided'}.")
        counts = matter.get("category_counts", {})
        lines.append("Category counts: " + "; ".join(f"{name}: {count}" for name, count in counts.items()) + ".")
        lines.append(f"Total category entries: {sum(counts.values())}. Categories may overlap; this is not a unique file count.")
    else:
        lines.append(f"No matter metadata was retrieved for {request['matter']}.")
    total = matter.get("category_counts", {}).get(request["category"]) if matter else None
    count_text = f"Downloaded {manifest['file_count']} out of {total} listed {request['category']} entries." if total is not None else f"Downloaded {manifest['file_count']} {request['category']} files."
    lines.extend(["", f"Retrieval status: {manifest['retrieval_status']}.", count_text,
                  f"Skipped entries: {len(manifest['unavailable'])}. Failed files: {len(manifest['failures'])}."])
    if manifest["retrieval_status"] == "access_blocked":
        lines.append("The website blocked access or requested human interaction. Retrieval has stopped.")
    warnings = sum(bool(item["validation"].get("warning") or item["validation"].get("parser_warning")
                        or item["validation"].get("extension_mismatch")) for item in manifest["files"])
    if warnings:
        lines.append(f"{warnings} downloaded files have source format warnings, preserved in the manifest.")
    if attachment_state == "attached":
        lines.append("The ZIP is attached. Its manifest lists original filenames, metadata, and file hashes.")
    elif attachment_state == "oversized":
        lines.append(f"The ZIP is {package['archive']['bytes']} bytes and exceeds the configured email size limit. "
                     "No ZIP is attached. Please contact the agent operator to arrange another delivery method.")
    else:
        lines.append("There are no completed files to attach.")
    lines.extend(["", "Senpilot document agent"])
    return "\n".join(lines)
