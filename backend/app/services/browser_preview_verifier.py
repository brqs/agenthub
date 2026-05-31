"""Browser-level verification for platform-managed workspace previews."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from app.core.config import settings

DEFAULT_VIEWPORTS: dict[str, tuple[int, int]] = {
    "desktop": (1366, 900),
    "mobile": (390, 844),
}


class BrowserPreviewVerifyDisabledError(RuntimeError):
    """Raised when browser verification is disabled."""


class BrowserPreviewVerifyError(RuntimeError):
    """Raised when browser verification cannot run."""


class BrowserPreviewVerifier:
    """Run deterministic Chromium checks against a preview URL."""

    async def verify(
        self,
        *,
        conversation_id: UUID,
        url: str,
        required_text: list[str] | None = None,
        viewports: list[str] | None = None,
        click_buttons: bool = True,
        max_clicks: int = 5,
    ) -> dict[str, Any]:
        if not settings.browser_verify_enabled:
            raise BrowserPreviewVerifyDisabledError("browser verification is disabled")
        started_at = time.monotonic()
        viewport_names = _normalize_viewports(viewports)
        required = _normalize_required_text(required_text)
        max_clicks = max(0, min(int(max_clicks), 10))
        screenshot_dir = Path(settings.browser_verify_screenshot_dir) / str(conversation_id)
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - environment-specific
            raise BrowserPreviewVerifyError("playwright is not installed") from exc

        checks: dict[str, bool] = {}
        issues: list[dict[str, Any]] = []
        screenshots: dict[str, str] = {}
        console_errors: list[str] = []
        page_errors: list[str] = []
        failed_requests: list[str] = []
        parsed_preview = urlparse(url)
        timeout_ms = max(settings.browser_verify_timeout_seconds, 1) * 1000

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                for name in viewport_names:
                    width, height = DEFAULT_VIEWPORTS[name]
                    page = await browser.new_page(
                        viewport={"width": width, "height": height},
                    )
                    page.on(
                        "console",
                        lambda msg: console_errors.append(msg.text)
                        if msg.type == "error"
                        else None,
                    )
                    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
                    page.on(
                        "requestfailed",
                        lambda request: failed_requests.append(request.url)
                        if _same_origin(parsed_preview, request.url)
                        else None,
                    )
                    page.on(
                        "response",
                        lambda response: failed_requests.append(
                            f"{response.status} {response.url}"
                        )
                        if response.status >= 400
                        and _same_origin(parsed_preview, response.url)
                        else None,
                    )
                    try:
                        response = await page.goto(
                            url,
                            wait_until="load",
                            timeout=timeout_ms,
                        )
                        checks[f"{name}_http_ok"] = bool(
                            response is not None and response.status < 400
                        )
                        await page.wait_for_timeout(500)
                    except Exception as exc:
                        checks[f"{name}_http_ok"] = False
                        issues.append(
                            {
                                "viewport": name,
                                "code": "navigation_failed",
                                "message": str(exc),
                            }
                        )
                        await page.close()
                        continue

                    body_metrics = await page.evaluate(
                        """() => {
                            const body = document.body;
                            const doc = document.documentElement;
                            return {
                                text: (body && body.innerText || '').trim(),
                                bodyWidth: body ? Math.ceil(body.getBoundingClientRect().width) : 0,
                                bodyHeight: body
                                  ? Math.ceil(body.getBoundingClientRect().height)
                                  : 0,
                                scrollWidth: doc ? doc.scrollWidth : 0,
                                viewportWidth: window.innerWidth,
                                visibleElements: Array.from(document.querySelectorAll('body *'))
                                  .filter((el) => {
                                    const rect = el.getBoundingClientRect();
                                    const style = window.getComputedStyle(el);
                                    return rect.width > 0 && rect.height > 0
                                      && style.visibility !== 'hidden'
                                      && style.display !== 'none';
                                  }).length,
                            };
                        }"""
                    )
                    text = str(body_metrics.get("text") or "")
                    checks[f"{name}_body_visible"] = (
                        int(body_metrics.get("bodyWidth") or 0) > 0
                        and int(body_metrics.get("bodyHeight") or 0) > 0
                        and int(body_metrics.get("visibleElements") or 0) > 0
                    )
                    checks[f"{name}_sufficient_text"] = len(text) >= 20
                    if name == "mobile":
                        checks["mobile_no_horizontal_overflow"] = (
                            int(body_metrics.get("scrollWidth") or 0)
                            <= int(body_metrics.get("viewportWidth") or 0) + 8
                        )
                    for item in required:
                        key = f"{name}_text_{_safe_key(item)}"
                        checks[key] = item.lower() in text.lower()

                    screenshot_path = screenshot_dir / f"{name}.png"
                    screenshot_bytes = await page.screenshot(
                        path=str(screenshot_path),
                        full_page=True,
                    )
                    screenshots[name] = str(screenshot_path)
                    checks[f"{name}_screenshot_nonempty"] = len(screenshot_bytes) > 1000
                    checks[f"{name}_screenshot_varied"] = len(set(screenshot_bytes)) > 32

                    if click_buttons:
                        clicked = await _click_visible_targets(page, max_clicks)
                        checks[f"{name}_click_targets_ok"] = clicked > 0 if max_clicks > 0 else True
                    await page.close()
            finally:
                await browser.close()

        checks["no_console_errors"] = not console_errors
        checks["no_page_errors"] = not page_errors
        checks["no_failed_requests"] = not failed_requests
        _collect_issues(checks, issues, console_errors, page_errors, failed_requests)
        passed = all(checks.values()) if checks else False
        report = {
            "passed": passed,
            "checks": checks,
            "issues": issues,
            "screenshots": screenshots,
            "console_errors": console_errors,
            "page_errors": page_errors,
            "failed_requests": failed_requests,
            "duration_ms": int((time.monotonic() - started_at) * 1000),
            "report_path": str(screenshot_dir / "report.json"),
        }
        (screenshot_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return report


async def _click_visible_targets(page: Any, max_clicks: int) -> int:
    if max_clicks <= 0:
        return 0
    locator = page.locator(
        "button, [role=button], input[type=button], input[type=submit], a[href]"
    )
    count = await locator.count()
    clicked = 0
    for index in range(count):
        if clicked >= max_clicks:
            break
        target = locator.nth(index)
        try:
            visible = await target.is_visible(timeout=500)
            if visible:
                await target.click(timeout=1000, trial=False)
                clicked += 1
                await page.wait_for_timeout(150)
        except Exception as exc:
            _ = exc
    return clicked


def _normalize_viewports(viewports: list[str] | None) -> list[str]:
    if not viewports:
        return ["desktop", "mobile"]
    normalized: list[str] = []
    for item in viewports:
        if item in DEFAULT_VIEWPORTS and item not in normalized:
            normalized.append(item)
    return normalized or ["desktop", "mobile"]


def _normalize_required_text(required_text: list[str] | None) -> list[str]:
    if not required_text:
        return []
    output: list[str] = []
    for item in required_text:
        if isinstance(item, str) and item.strip() and item.strip() not in output:
            output.append(item.strip())
    return output[:20]


def _safe_key(text: str) -> str:
    key = "".join(char.lower() if char.isalnum() else "_" for char in text)[:32]
    return key.strip("_") or "text"


def _same_origin(parsed_preview: Any, url: str) -> bool:
    parsed = urlparse(url)
    return bool(
        parsed.scheme == parsed_preview.scheme
        and parsed.hostname == parsed_preview.hostname
        and parsed.port == parsed_preview.port
    )


def _collect_issues(
    checks: dict[str, bool],
    issues: list[dict[str, Any]],
    console_errors: list[str],
    page_errors: list[str],
    failed_requests: list[str],
) -> None:
    for name, passed in checks.items():
        if not passed:
            issues.append({"code": name, "message": f"check failed: {name}"})
    for message in console_errors:
        issues.append({"code": "console_error", "message": message})
    for message in page_errors:
        issues.append({"code": "page_error", "message": message})
    for url in failed_requests:
        issues.append({"code": "failed_request", "message": url})
