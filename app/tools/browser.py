"""Browser helpers. They do not bypass login, CAPTCHA, or MFA."""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel

from app.storage.models import Preflight, ToolResult
from app.tools.base import ToolContext


class UrlArgs(BaseModel):
    url: str


def validate_public_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PermissionError("Only a full http or https address can be opened")
    if parsed.username or parsed.password:
        raise PermissionError("The address cannot contain an account or password")
    return url.strip()


def preflight_browser(args: UrlArgs, _ctx: ToolContext) -> Preflight:
    return Preflight(
        summary="Open the browser",
        paths=[args.url],
        impact=f"A visible browser will open {args.url}. The mouse can then click controls on the page.",
    )


def open_browser(args: UrlArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("Opening the browser requires confirmation for this action")
    url = validate_public_url(args.url)
    browser = ctx.platform.open_browser(url)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="Opened the page in a visible browser",
        message=f"Opened {url}",
        data={"url": url, "browser": str(browser), "issued": True, "confirmed": True},
    )


def open_url(args: UrlArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("Opening this address requires confirmation")
    url = validate_public_url(args.url)
    ctx.platform.open_url(url)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="Handed the allowed address to the system default browser",
        message=f"Opened {url}",
        data={"url": url, "issued": True, "confirmed": True},
    )


def read_page_title(args: UrlArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("Reading this page requires confirmation for this address")
    url = validate_public_url(args.url)
    try:
        title = ctx.platform.read_page_title(url, ctx.cancel_event)
    except Exception as exc:
        return ToolResult(ok=False, error=str(exc), error_code="window_not_ready")
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="Only the page title was read",
        message=f"Page title: {title}",
        data={"url": url, "title": title[:200], "count": 1},
    )
