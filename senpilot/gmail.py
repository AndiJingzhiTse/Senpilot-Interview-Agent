"""Dedicated Gmail inbox access through Google's OAuth client libraries."""

import argparse
import base64
from email import policy
from email.parser import BytesParser
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"]


def save_token(credentials, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(credentials.to_json(), encoding="utf-8")
    temporary.replace(path)


def load_credentials(path: Path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    if not path.exists():
        raise RuntimeError("No Gmail token found; run python -m senpilot.gmail first")
    credentials = Credentials.from_authorized_user_file(str(path))
    if not credentials.has_scopes(SCOPES):
        raise RuntimeError("The Gmail token lacks required scopes; authorize again")
    if not credentials.valid:
        if not credentials.refresh_token:
            raise RuntimeError("The Gmail token cannot refresh; authorize again")
        credentials.refresh(Request())
        save_token(credentials, path)
    return credentials


def create_service(credentials):
    import httplib2
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build
    return build("gmail", "v1", http=AuthorizedHttp(credentials, http=httplib2.Http(timeout=60)), cache_discovery=False)


class Gmail:
    def __init__(self, token: Path, *, service=None):
        if service is None:
            service = create_service(load_credentials(token))
        self.service = service
        self.address = service.users().getProfile(userId="me").execute(num_retries=2)["emailAddress"]

    def incoming(self, known: set[str], maximum=20, allowed_senders: set[str] | None = None):
        # None explicitly allows any sender; an empty set accepts nobody.
        if allowed_senders is not None and not allowed_senders:
            return
        token, remaining = None, maximum
        query = "is:unread in:inbox -from:me"
        if allowed_senders:
            query += " {" + " ".join(f"from:{address}" for address in sorted(allowed_senders)) + "}"
        while remaining:
            result = self.service.users().messages().list(
                userId="me", q=query, maxResults=100, pageToken=token).execute(num_retries=2)
            for item in result.get("messages", []):
                source_id = f"gmail:{self.address.casefold()}:{item['id']}"
                if source_id in known:
                    continue
                metadata = self.service.users().messages().get(userId="me", id=item["id"], format="metadata").execute(num_retries=2)
                if metadata.get("sizeEstimate", 0) > 1024 * 1024:
                    raw = b"Auto-Submitted: auto-generated\r\n\r\nIgnored incoming request above 1 MB."
                else:
                    full = self.service.users().messages().get(userId="me", id=item["id"], format="raw").execute(num_retries=2)
                    encoded = full["raw"]
                    raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
                yield source_id, raw, metadata.get("threadId")
                remaining -= 1
                if not remaining:
                    return
            token = result.get("nextPageToken")
            if not token:
                return

    def send(self, raw: bytes, thread_id: str | None = None):
        message = BytesParser(policy=policy.default).parsebytes(raw)
        if message["From"].addresses[0].addr_spec.casefold() != self.address.casefold():
            raise ValueError("The reply From address does not match the authorized Gmail account")
        body = {"raw": base64.urlsafe_b64encode(raw).decode("ascii")}
        if thread_id:
            body["threadId"] = thread_id
        # A lost response can mean delivery happened. Do not repeat a send automatically.
        return self.service.users().messages().send(userId="me", body=body).execute(num_retries=0)


def main():
    parser = argparse.ArgumentParser(description="Authorize the agent's dedicated Gmail account")
    parser.add_argument("--client", type=Path, default=Path("artifacts/oauth/credentials.json"))
    parser.add_argument("--token", type=Path, default=Path("artifacts/oauth/token.json"))
    parser.add_argument("--agent", help="Expected agent Gmail address; reject a different authorized account")
    args = parser.parse_args()
    if not args.client.is_file():
        parser.error("Save the Desktop OAuth client JSON at --client; see docs/email-setup.md")
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(args.client), SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    address = Gmail(args.token, service=create_service(credentials)).address
    if args.agent and address.casefold() != args.agent.casefold():
        parser.error("The authorized account differs from --agent; token was not saved")
    save_token(credentials, args.token)
    print(f"Authorized agent mailbox: {address}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
