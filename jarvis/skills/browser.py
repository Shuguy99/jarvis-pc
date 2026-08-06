"""Автоматизация браузера: LLM собирает сценарий из простых шагов Playwright."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from ..config import BrowserConfig
from .registry import Skill, object_schema

if TYPE_CHECKING:  # pragma: no cover - playwright опционален
    from playwright.sync_api import BrowserContext, Page, Playwright

log = logging.getLogger(__name__)

T = TypeVar("T")

# Разрешённые клавиши для browser_press (защита от произвольного ввода).
_ALLOWED_KEYS = frozenset({
    "Enter", "Tab", "Escape", "Backspace", "Delete", "Home", "End",
    "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown",
    "PageUp", "PageDown", "Control+a", "Control+c", "Control+v",
    "Control+x", "Control+z", "Control+A", "Control+C", "Control+V",
    "Control+X", "Control+Z", "Control+Enter", "Shift+Tab",
    "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x", "y", "z",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "Space", "Minus", "Equal", "BracketLeft", "BracketRight",
    "Backslash", "Semicolon", "Quote", "Backquote", "Comma", "Period", "Slash",
})

INSTALL_HINT = (
    "Playwright не установлен, сэр. Выполните: pip install playwright "
    "и затем playwright install chromium."
)


class BrowserSession:
    """Один живой браузер с сохранённым профилем.

    Playwright в синхронном режиме требует один и тот же поток, поэтому все
    операции выполняются в выделенном однопоточном исполнителе.
    """

    def __init__(self, config: BrowserConfig) -> None:
        self.config = config
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser")
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def _submit(self, work: Callable[[], T]) -> T:
        """Выполняет операцию в потоке браузера."""
        return self._pool.submit(work).result()

    def _ensure_page(self) -> Page:
        """Запускает браузер при первом обращении и возвращает страницу."""
        if self._page is not None:
            return self._page
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(INSTALL_HINT) from exc
        self._playwright = sync_playwright().start()
        engines = {
            "chromium": self._playwright.chromium,
            "firefox": self._playwright.firefox,
            "webkit": self._playwright.webkit,
        }
        engine = engines.get(self.config.engine, self._playwright.chromium)
        Path(self.config.user_data_dir).mkdir(parents=True, exist_ok=True)
        self._context = engine.launch_persistent_context(
            self.config.user_data_dir,
            headless=self.config.headless,
        )
        self._context.set_default_timeout(self.config.timeout_ms)
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        return self._page

    def _run(self, work: Callable[[Page], str]) -> str:
        """Обёртка: гарантирует страницу и превращает ошибки в понятный текст."""

        def job() -> str:
            page = self._ensure_page()
            return work(page)

        try:
            return self._submit(job)
        except RuntimeError as exc:
            return str(exc)
        except Exception as exc:
            log.exception("Ошибка браузера")
            return f"Браузер не справился: {exc}"

    def open(self, url: str) -> str:
        """Открывает страницу."""
        target = url if "://" in url else f"https://{url}"

        def work(page: Page) -> str:
            page.goto(target, wait_until="domcontentloaded")
            return f"Открыл {page.title() or target}."

        return self._run(work)

    def click(self, text: str) -> str:
        """Нажимает на элемент с указанным текстом."""

        def work(page: Page) -> str:
            page.get_by_text(text, exact=False).first.click()
            page.wait_for_load_state("domcontentloaded")
            return f"Нажал «{text}»."

        return self._run(work)

    def fill(self, field: str, text: str) -> str:
        """Заполняет поле, найденное по подписи, placeholder или роли."""

        def work(page: Page) -> str:
            for locator in (
                page.get_by_label(field, exact=False),
                page.get_by_placeholder(field, exact=False),
                page.get_by_role("textbox", name=field),
            ):
                try:
                    if locator.count():
                        locator.first.fill(text)
                        return f"Ввёл текст в поле «{field}»."
                except Exception:
                    continue
            # Fallback: пробуем как CSS-селектор.
            try:
                page.locator(field).first.fill(text)
                return f"Ввёл текст в «{field}»."
            except Exception as exc:
                return f"Не нашёл поле «{field}»: {exc}"

        return self._run(work)

    def press(self, key: str) -> str:
        """Нажимает клавишу на странице, например Enter."""
        if key not in _ALLOWED_KEYS:
            return f"Клавиша «{key}» не в списке разрешённых, сэр."

        def work(page: Page) -> str:
            page.keyboard.press(key)
            page.wait_for_load_state("domcontentloaded")
            return f"Нажал {key}."

        return self._run(work)

    def read(self, selector: str = "") -> str:
        """Читает видимый текст страницы или конкретного блока."""

        def work(page: Page) -> str:
            target = page.locator(selector) if selector else page.locator("body")
            if not target.count():
                return f"Ничего не нашёл по «{selector}», сэр."
            text = " ".join(target.first.inner_text().split())
            if not text:
                return "Блок пустой, сэр."
            return text[: self.config.max_text_chars]

        return self._run(work)

    def close(self) -> str:
        """Закрывает браузер и освобождает ресурсы."""
        if self._page is None:
            return "Браузер и так закрыт, сэр."

        def job() -> str:
            if self._context is not None:
                self._context.close()
            if self._playwright is not None:
                self._playwright.stop()
            self._page = self._context = self._playwright = None
            return "Браузер закрыт, сэр."

        try:
            return self._submit(job)
        except Exception as exc:
            log.exception("Не удалось закрыть браузер")
            return f"Не удалось закрыть браузер: {exc}"

    def shutdown(self) -> None:
        """Гасит браузер и поток при выходе из приложения."""
        if self._page is not None:
            try:
                self.close()
            except Exception:
                log.exception("Не удалось закрыть браузер при shutdown")
        self._pool.shutdown(wait=False, cancel_futures=True)


def build_skills(config: BrowserConfig) -> tuple[list[Skill], BrowserSession]:
    """Создаёт навыки управления браузером и саму сессию."""
    session = BrowserSession(config)
    if not config.enabled:
        return [], session
    skills = [
        Skill(
            name="browser_open",
            description=(
                "Открыть страницу в управляемом браузере (профиль сохраняется, "
                "логины не сбрасываются). Первый шаг любого сценария в интернете."
            ),
            parameters=object_schema(
                {"url": {"type": "string", "description": "Адрес страницы"}},
                required=["url"],
            ),
            handler=session.open,
        ),
        Skill(
            name="browser_click",
            description="Нажать в управляемом браузере на ссылку или кнопку с этим текстом.",
            parameters=object_schema(
                {"text": {"type": "string", "description": "Видимый текст элемента"}},
                required=["text"],
            ),
            handler=session.click,
        ),
        Skill(
            name="browser_fill",
            description="Ввести текст в поле управляемого браузера, найдя его по подписи.",
            parameters=object_schema(
                {
                    "field": {
                        "type": "string",
                        "description": "Подпись, placeholder или CSS-селектор поля",
                    },
                    "text": {"type": "string", "description": "Что ввести"},
                },
                required=["field", "text"],
            ),
            handler=session.fill,
        ),
        Skill(
            name="browser_press",
            description="Нажать клавишу в управляемом браузере, например Enter.",
            parameters=object_schema(
                {"key": {"type": "string", "description": "Название клавиши"}},
                required=["key"],
            ),
            handler=session.press,
        ),
        Skill(
            name="browser_read",
            description=(
                "Прочитать текст открытой страницы, чтобы найти в нём ответ "
                "(статус заказа, цену, результат поиска)."
            ),
            parameters=object_schema(
                {
                    "selector": {
                        "type": "string",
                        "description": "CSS-селектор блока, пусто — вся страница",
                    }
                }
            ),
            handler=lambda selector="": session.read(selector),
        ),
        Skill(
            name="browser_close",
            description="Закрыть управляемый браузер.",
            parameters=object_schema({}),
            handler=session.close,
        ),
    ]
    return skills, session
