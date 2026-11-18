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
        raise PermissionError("只允许打开完整的 http 或 https 网址")
    if parsed.username or parsed.password:
        raise PermissionError("网址中不能包含账号或密码")
    return url.strip()


def preflight_browser(args: UrlArgs, _ctx: ToolContext) -> Preflight:
    return Preflight(
        summary="打开浏览器",
        paths=[args.url],
        impact=f"将打开可见浏览器访问 {args.url}。随后可以用鼠标点击页面上的控件。",
    )


def open_browser(args: UrlArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("打开浏览器需要这次操作的确认")
    url = validate_public_url(args.url)
    browser = ctx.platform.open_browser(url)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="已用可见浏览器打开页面",
        message=f"已打开 {url}",
        data={"url": url, "browser": str(browser), "issued": True, "confirmed": True},
    )


def open_url(args: UrlArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("打开网页需要这次网址的确认")
    url = validate_public_url(args.url)
    ctx.platform.open_url(url)
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="已把允许的网址交给系统默认浏览器",
        message=f"已打开 {url}",
        data={"url": url, "issued": True, "confirmed": True},
    )


def read_page_title(args: UrlArgs, ctx: ToolContext) -> ToolResult:
    if not ctx.approved:
        raise PermissionError("读取网页需要这次网址的确认")
    url = validate_public_url(args.url)
    try:
        title = ctx.platform.read_page_title(url, ctx.cancel_event)
    except Exception as exc:
        return ToolResult(ok=False, error=str(exc), error_code="window_not_ready")
    return ToolResult(
        ok=True,
        verified=True,
        verification_detail="只读取了页面标题",
        message=f"页面标题: {title}",
        data={"url": url, "title": title[:200], "count": 1},
    )
