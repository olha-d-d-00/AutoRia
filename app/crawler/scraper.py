from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

import asyncio
from typing import List
import httpx
from bs4 import BeautifulSoup

BASE = "https://auto.ria.com"
SEARCH = "https://auto.ria.com/uk/car/used/"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8",
}

async def get_html(client: httpx.AsyncClient, url: str, retries: int = 3) -> str:
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            r = await client.get(url, headers=HEADERS)
            r.raise_for_status()
            return r.text
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError) as e:
            last_err = e
            await asyncio.sleep(0.8 * attempt)  # лёгкий backoff
        except httpx.HTTPStatusError as e:
            # 403/404/5xx — тоже не валим весь прогон
            last_err = e
            await asyncio.sleep(0.5 * attempt)

    raise last_err


async def scrape_list_pages(limit_pages: int | None = None) -> List[str]:
    async with httpx.AsyncClient(
        headers=HEADERS,
        follow_redirects=True,
        timeout=30,
    ) as client:
        first_html = await get_html(client, SEARCH)
        soup = BeautifulSoup(first_html, "html.parser")

        urls = set()
        for a in soup.select("a.address"):
            href = a.get("href")
            if href:
                urls.add(href)

        max_page = 1
        for a in soup.select("a.page-link"):
            try:
                max_page = max(max_page, int(a.get_text(strip=True)))
            except Exception:
                pass

        if limit_pages is not None:
            max_page = min(max_page, limit_pages)

        for page in range(2, max_page + 1):
            page_url = f"{SEARCH}?page={page}"
            html = await get_html(client, page_url)
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.select("a.address"):
                href = a.get("href")
                if href:
                    urls.add(href)

        result = []
        for u in urls:
            if u.startswith("http"):
                result.append(u)
            else:
                result.append(BASE + u)

        # фильтр: только б/у карточки
        result = [u for u in result if "/uk/auto_" in u and "/newauto/" not in u]
        return result


async def fetch_phone_number(
    client: httpx.AsyncClient,
    auto_id: int,
    expires: int,
    hash_: str,
) -> Optional[str]:
    """
    Рабочий сценарий AutoRia: телефон выдаётся через endpoint:
    https://auto.ria.com/users/phones/{auto_id}?expires=...&hash=...

    Возвращаем телефон цифрами (строкой), например: "380631234567"
    """
    url = f"{BASE}/users/phones/{auto_id}?expires={expires}&hash={hash_}"
    r = await client.get(url, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        return None

    try:
        data = r.json()
    except Exception:
        return None

    phone = (
        data.get("formattedPhoneNumber")
        or data.get("phone")
        or data.get("phoneNumber")
    )
    if not phone:
        return None

    digits = "".join(ch for ch in str(phone) if ch.isdigit())

    # нормализация UA
    if len(digits) == 10 and digits.startswith("0"):
        return "38" + digits
    if len(digits) == 12 and digits.startswith("38"):
        return digits

    return digits or None
