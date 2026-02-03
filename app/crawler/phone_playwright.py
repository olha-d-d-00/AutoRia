# app/crawler/phone_playwright.py
import re
from typing import Optional

from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError

PHONE_RE = re.compile(r"(?:\+?38)?0?\d{9}")  # грубо ловим UA формат


def _digits_only(s: str) -> str:
    return re.sub(r"\D+", "", s or "")


def _normalize_phone(raw: str) -> Optional[int]:
    digits = _digits_only(raw)
    if not digits:
        return None

    # варианты:
    # 0XXXXXXXXX (10) -> 38 + ...
    # 380XXXXXXXXX (12) -> ok
    # +380... -> digits already 380...
    if len(digits) == 10 and digits.startswith("0"):
        digits = "38" + digits

    if len(digits) == 12 and digits.startswith("38"):
        return int(digits)

    # если где-то внутри проскочило 380...
    m = re.search(r"38\d{10}", digits)
    if m:
        return int(m.group(0))

    return None


async def _click_if_exists(page, selector: str, timeout_ms: int = 1500) -> bool:
    loc = page.locator(selector)
    if await loc.count() > 0:
        try:
            await loc.first.click(timeout=timeout_ms, force=True)
            return True
        except Exception:
            return False
    return False


async def _accept_banners(page) -> None:
    # 1) Нотифаер/баннер (часто мешает клику)
    await _click_if_exists(page, "label[for='c-notifier-close']", 1500)
    await _click_if_exists(page, "#c-notifier-close", 1500)

    # 2) Funding Choices / consent (fc-*)
    # ВАЖНО: иногда кнопка не button, а div с role=button — поэтому несколько вариантов
    candidates = [
        "button.fc-cta-consent",
        "button[class*='fc-cta-consent']",
        "div.fc-cta-consent",
        "div[class*='fc-cta-consent']",
        "button:has-text('Прийняти')",
        "button:has-text('Прийняти все')",
        "button:has-text('Погоджуюсь')",
        "button:has-text('Accept')",
        "button:has-text('Accept all')",
        "#onetrust-accept-btn-handler",
        "button#onetrust-accept-btn-handler",
    ]
    for sel in candidates:
        ok = await _click_if_exists(page, sel, 2000)
        if ok:
            await page.wait_for_timeout(500)
            break


async def get_phone_via_playwright(url: str) -> Optional[int]:
    """
    Рабочий подход под твой кейс:
    - НЕ ищем #autoPhone (его нет в DOM)
    - кликаем "показати" рядом с замаскированным номером (span.mhide + a)
    - читаем номер из DOM после раскрытия
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="uk-UA",
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # баннеры/куки
            await _accept_banners(page)

            # чуть скроллим, чтобы блок контактов дорендерился
            await page.mouse.wheel(0, 900)
            await page.wait_for_timeout(500)

            # Ключевой селектор: на AutoRia обычно так:
            # <span class="mhide">***</span><a>показати</a>
            show_link = page.locator("span.mhide + a")

            # fallback-и, если верстка другая
            show_fallbacks = [
                "a:has-text('показати')",
                "a:has-text('Показати')",
                "a:has-text('Показать')",
                "button:has-text('Показати телефон')",
                "button:has-text('Показать телефон')",
            ]

            clicked = False

            if await show_link.count() > 0:
                try:
                    await show_link.first.scroll_into_view_if_needed()
                    await show_link.first.click(timeout=8000, force=True)
                    clicked = True
                except Exception:
                    clicked = False

            if not clicked:
                for sel in show_fallbacks:
                    loc = page.locator(sel)
                    if await loc.count() > 0:
                        try:
                            await loc.first.scroll_into_view_if_needed()
                            await loc.first.click(timeout=8000, force=True)
                            clicked = True
                            break
                        except Exception:
                            pass

            if not clicked:
                return None

            # После клика телефон обычно появляется в блоке list-phone
            # Пробуем несколько точек, где он реально всплывает.
            phone_locators = [
                "div.list-phone",                              # общий контейнер
                "div.list-phone div",                          # внутри часто лежит номер
                "div.list-phone a:nth-of-type(2) + div",       # как в реальном примере
                "div.list-phone strong",
                "a[href^='tel:']",
            ]

            # ждём до 12 секунд, проверяя разные локаторы
            for _ in range(24):
                for sel in phone_locators:
                    loc = page.locator(sel)
                    if await loc.count() == 0:
                        continue
                    try:
                        txt = (await loc.first.inner_text(timeout=500)).strip()
                    except Exception:
                        continue

                    phone = _normalize_phone(txt)
                    if phone:
                        return phone

                await page.wait_for_timeout(500)

            # последний шанс: поиск по всему HTML
            html = await page.content()
            m = PHONE_RE.search(html)
            if m:
                phone = _normalize_phone(m.group(0))
                if phone:
                    return phone

            return None

        except PWTimeoutError:
            return None
        finally:
            await page.close()
            await context.close()
            await browser.close()
