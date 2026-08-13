"""Tests for how `PageCrawler` drives `<select>` elements over CDP.

These stub the CDP session rather than launching a browser, so they cover the
handle lifecycle — resolve, call, release — without a browser install. The
lifecycle is the interesting part: selecting an option frequently navigates,
and navigation destroys the execution context that owns the handle.
"""

from typing import Any, Awaitable, Callable

import pytest
from playwright.async_api import Error as PlaywrightError

from inspect_tool_support._remote_tools._web_browser import playwright_page_crawler
from inspect_tool_support._remote_tools._web_browser.playwright_page_crawler import (
    PageCrawler,
)

# value/label/disabled triples as _READ_SELECT_OPTIONS_JS reports them
_OPTIONS = [
    ["", "Choose an option", False],
    ["option1", "Option 1", False],
    ["option3", "Option 3", False],
]

_OBJECT_ID = "object-1"


class FakeCDPSession:
    """A CDP session serving a page with a single `<select>`."""

    def __init__(self, on_select: Callable[[], Awaitable[None]] | None = None) -> None:
        self._on_select = on_select
        self.methods: list[str] = []
        self.released = False
        self.selected_index: int | None = None
        self.submitted: bool | None = None
        # Set once a navigation has torn down the page's execution context.
        self.context_destroyed = False

    async def send(self, method: str, params: dict[str, Any] | None = None) -> Any:
        params = params or {}
        self.methods.append(method)

        if method in ("Accessibility.enable", "DOM.enable"):
            return {}

        if method == "DOM.resolveNode":
            return {"object": {"objectId": _OBJECT_ID}}

        if method == "Runtime.callFunctionOn":
            assert params["objectId"] == _OBJECT_ID
            if "selectedIndex" in params["functionDeclaration"]:
                self.selected_index = params["arguments"][0]["value"]
                self.submitted = params["arguments"][1]["value"]
                if self._on_select is not None:
                    await self._on_select()
                return {"result": {"value": None}}
            return {"result": {"value": _OPTIONS}}

        if method == "Runtime.releaseObject":
            if self.context_destroyed:
                raise PlaywrightError(
                    "Protocol error (Runtime.releaseObject): "
                    "Cannot find context with specified id"
                )
            self.released = True
            return {}

        raise AssertionError(f"unexpected CDP method: {method}")


class FakeBrowserContext:
    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[Any], Awaitable[None]]] = {}

    def once(self, event: str, handler: Callable[[Any], Awaitable[None]]) -> None:
        self.handlers[event] = handler


class FakePage:
    def __init__(self) -> None:
        self.context = FakeBrowserContext()
        self.handlers: dict[str, Callable[[Any], Awaitable[None]]] = {}
        self.url = "https://example.test/form.html"

    def once(self, event: str, handler: Callable[[Any], Awaitable[None]]) -> None:
        self.handlers[event] = handler

    async def wait_for_load_state(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def navigate(self) -> None:
        """Fires the navigation listener the crawler registered."""
        handler = self.handlers.get("framenavigated")
        assert handler is not None, "crawler did not listen for navigation"
        await handler(None)


@pytest.fixture
def anyio_backend() -> str:
    """Pins these tests to asyncio.

    Overrides anyio's fixture, which otherwise parametrizes over every
    installed backend. `PageCrawler` awaits navigation on an `asyncio.Future`
    via `asyncio.wait_for`, so it cannot run under trio.
    """
    return "asyncio"


class FakeNode:
    """An element as the accessibility tree exposes it."""

    def __init__(self, role: str = "combobox") -> None:
        self.role = role
        self.backend_dom_node_id = 42


def _crawler(
    page: FakePage, cdp_session: FakeCDPSession, role: str = "combobox"
) -> PageCrawler:
    crawler = PageCrawler(page, cdp_session, 1.0)  # type: ignore[arg-type]
    crawler.lookup_node = lambda element_id: FakeNode(role)  # type: ignore[assignment,return-value]
    return crawler


@pytest.mark.anyio
async def test_submit_survives_navigation_destroying_the_handle():
    """Submitting a dropdown's form must not report the successful submit as an error."""
    page = FakePage()

    async def navigate() -> None:
        await page.navigate()
        cdp_session.context_destroyed = True

    cdp_session = FakeCDPSession(on_select=navigate)

    await _crawler(page, cdp_session).submit(1, "option3")

    assert cdp_session.selected_index == 2
    assert cdp_session.submitted is True
    # the release was attempted, failed, and was absorbed
    assert "Runtime.releaseObject" in cdp_session.methods
    assert not cdp_session.released


@pytest.mark.anyio
async def test_type_selects_option_and_releases_handle(monkeypatch):
    """Without a navigation the handle is still live, so it gets released."""
    monkeypatch.setattr(playwright_page_crawler, "_WAIT_FOR_NAVIGATION_TIME", 0.05)
    page = FakePage()
    cdp_session = FakeCDPSession()

    await _crawler(page, cdp_session).type(1, "Option 1")

    assert cdp_session.selected_index == 1
    assert cdp_session.submitted is False
    assert cdp_session.released


@pytest.mark.anyio
async def test_a_failed_selection_is_not_masked_by_a_failed_release():
    """The page's error must survive the release attempt in the `finally`."""
    page = FakePage()

    async def fail_after_destroying_context() -> None:
        cdp_session.context_destroyed = True
        raise RuntimeError("the page function exploded")

    cdp_session = FakeCDPSession(on_select=fail_after_destroying_context)

    with pytest.raises(RuntimeError, match="the page function exploded"):
        await _crawler(page, cdp_session).type(1, "option3")


@pytest.mark.anyio
async def test_unmatched_text_reports_the_available_options(monkeypatch):
    monkeypatch.setattr(playwright_page_crawler, "_WAIT_FOR_NAVIGATION_TIME", 0.05)
    page = FakePage()
    cdp_session = FakeCDPSession()

    with pytest.raises(ValueError) as excinfo:
        await _crawler(page, cdp_session).type(1, "Option 4")

    message = str(excinfo.value)
    assert "Option 4" in message
    assert '"Option 3" (value: "option3")' in message
    # nothing was selected, and the handle was still cleaned up
    assert cdp_session.selected_index is None
    assert cdp_session.released


@pytest.mark.anyio
async def test_a_non_combobox_never_reaches_the_cdp_session():
    """Text inputs must not pay the resolve round trips to learn they aren't dropdowns."""
    cdp_session = FakeCDPSession()
    crawler = _crawler(FakePage(), cdp_session, role="textbox")

    assert await crawler._resolve_select(1) is None
    assert cdp_session.methods == []
