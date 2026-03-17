"""
Email Autoreply Skill
Fetches unread emails via IMAP and drafts context-aware replies via Grok.
Set EMAIL_IMAP_HOST, EMAIL_SMTP_HOST, EMAIL_ADDRESS, EMAIL_PASSWORD env vars.
"""

from __future__ import annotations

import asyncio
import email
import imaplib
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header


def _get_config() -> dict:
    return {
        "imap_host": os.environ.get("EMAIL_IMAP_HOST", ""),
        "imap_port": int(os.environ.get("EMAIL_IMAP_PORT", "993")),
        "smtp_host": os.environ.get("EMAIL_SMTP_HOST", ""),
        "smtp_port": int(os.environ.get("EMAIL_SMTP_PORT", "587")),
        "email": os.environ.get("EMAIL_ADDRESS", ""),
        "password": os.environ.get("EMAIL_PASSWORD", ""),
    }


def _decode_header_value(value: str) -> str:
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _fetch_email(email_id: str, cfg: dict) -> dict | None:
    """Fetch an email via IMAP. Returns parsed dict."""
    if not cfg["imap_host"] or not cfg["email"]:
        return {"error": "EMAIL_IMAP_HOST and EMAIL_ADDRESS not set"}

    try:
        context = ssl.create_default_context()
        with imaplib.IMAP4_SSL(cfg["imap_host"], cfg["imap_port"], ssl_context=context) as imap:
            imap.login(cfg["email"], cfg["password"])
            imap.select("INBOX")

            if email_id == "latest":
                _, messages = imap.search(None, "UNSEEN")
                ids = messages[0].split()
                if not ids:
                    return {"found": False, "message": "No unread emails"}
                target_id = ids[-1]
            else:
                target_id = email_id.encode()

            _, msg_data = imap.fetch(target_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            subject = _decode_header_value(msg.get("Subject", "(no subject)"))
            sender = msg.get("From", "")
            body = ""

            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", errors="replace")

            return {
                "id": target_id.decode(),
                "subject": subject,
                "from": sender,
                "body": body[:2000],
            }
    except Exception as e:
        return {"error": str(e)}


def _send_email(to: str, subject: str, body: str, cfg: dict) -> dict:
    """Send email via SMTP."""
    try:
        msg = MIMEMultipart()
        msg["From"] = cfg["email"]
        msg["To"] = to
        msg["Subject"] = f"Re: {subject}"
        msg.attach(MIMEText(body, "plain"))

        context = ssl.create_default_context()
        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as server:
            server.starttls(context=context)
            server.login(cfg["email"], cfg["password"])
            server.send_message(msg)

        return {"sent": True, "to": to, "subject": subject}
    except Exception as e:
        return {"sent": False, "error": str(e)}


async def run(params: dict) -> dict:
    """
    Main skill entrypoint.
    params:
      email_id: str  — specific ID or 'latest' (default)
      tone: str      — 'professional' | 'casual' | 'brief'
      send: bool     — actually send the reply
    """
    cfg = _get_config()
    email_id = params.get("email_id", "latest")
    tone = params.get("tone", "professional")
    should_send = params.get("send", False)

    # Fetch email in thread pool (blocking IMAP)
    loop = asyncio.get_event_loop()
    fetched = await loop.run_in_executor(None, _fetch_email, email_id, cfg)

    if not fetched or "error" in fetched:
        return fetched or {"error": "Could not fetch email"}

    if not fetched.get("found", True):
        return fetched

    # Draft reply with Grok
    try:
        import httpx
        import json as _json

        prompt = f"""\
Email from: {fetched['from']}
Subject: {fetched['subject']}
Body:
{fetched['body']}

---
Draft a {tone} reply to this email. Be concise and natural.
Do NOT include subject line or greetings header — just the body text.
"""

        from doppelganger.agents.grok_client import get_grok
        grok = get_grok()
        reply_text = await grok.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500,
        )

        result = {
            "email": fetched,
            "draft_reply": reply_text,
            "tone": tone,
            "sent": False,
        }

        if should_send and reply_text:
            send_result = await loop.run_in_executor(
                None, _send_email,
                fetched["from"], fetched["subject"], reply_text, cfg
            )
            result.update(send_result)

        return result

    except Exception as e:
        return {"error": f"Reply generation failed: {e}", "email": fetched}
