import json
import re
from typing import Optional, Dict, Any

import httpx
from bs4 import BeautifulSoup

PLATE_RE = re.compile(r"\b[A-ZА-ЯІЇЄ]{2}\s?\d{4}\s?[A-ZА-ЯІЇЄ]{2}\b")


def _safe_int(x) -> Optional[int]:
    try:
        if x is None:
            return None
        if isinstance(x, str):
            x = x.replace(" ", "").replace("\xa0", "").replace(",", ".")
        return int(float(x))
    except Exception:
        return None


def _digits_only(s: str) -> str:
    return re.sub(r"\D+", "", s or "")


def _pick_vehicle_jsonld(html: str) -> Dict[str, Any]:
    """
    Берём JSON-LD Vehicle с максимальным "смыслом".
    """
    soup = BeautifulSoup(html, "html.parser")
    best_obj = None
    best_score = -1

    for t in soup.select("script[type='application/ld+json']"):
        raw = (t.string or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue

        items = data if isinstance(data, list) else [data]
        for obj in items:
            if not isinstance(obj, dict):
                continue
            if obj.get("@type") != "Vehicle":
                continue

            score = 0
            if "offers" in obj:
                score += 3
            if "vehicleIdentificationNumber" in obj or "vin" in obj:
                score += 2
            if "mileageFromOdometer" in obj:
                score += 2
            if "image" in obj:
                score += 1

            if score > best_score:
                best_score = score
                best_obj = obj

    return best_obj or {}


def _extract_images_count(soup: BeautifulSoup, vehicle: Dict[str, Any], html: str) -> Optional[int]:
    # 1) JSON-LD
    img_field = vehicle.get("image")
    if isinstance(img_field, list) and img_field:
        return len(img_field)
    if isinstance(img_field, str) and img_field.strip():
        return 1

    # 2) regex
    patterns = [
        r'"countPhotos"\s*:\s*(\d+)',
        r'"photosCount"\s*:\s*(\d+)',
        r'"countPhoto"\s*:\s*(\d+)',
        r'"photoCount"\s*:\s*(\d+)',
        r'"count_images"\s*:\s*(\d+)',
        r'"photos"\s*:\s*\{\s*"count"\s*:\s*(\d+)',
    ]
    for p in patterns:
        m = re.search(p, html)
        if m:
            return int(m.group(1))

    # 3) DOM fallback
    ria_imgs = []
    for img in soup.select("img"):
        src = (img.get("src") or "").strip()
        if "cdn.riastatic.com" in src:
            ria_imgs.append(src)
    if ria_imgs:
        return len(set(ria_imgs))

    return None


def _extract_username(html: str) -> Optional[str]:
    # как ["userName","Volkswagen Центр"]
    m = re.search(r'\["userName"\s*,\s*"([^"]+)"\]', html)
    if m:
        return m.group(1).strip()

    # как "userName":"..."
    m = re.search(r'"userName"\s*:\s*"([^"]+)"', html)
    if m:
        return m.group(1).strip()

    return None


def _extract_price_usd(vehicle: Dict[str, Any], html: str) -> Optional[int]:
    offers = vehicle.get("offers")
    if isinstance(offers, dict):
        cur = offers.get("priceCurrency")
        pr = offers.get("price")
        if cur == "USD":
            return _safe_int(pr)

    m = re.search(r'"USD"\s*[:,]\s*"?(\d{2,7})"?', html)
    if m:
        return int(m.group(1))

    for p in [r'"priceUsd"\s*:\s*(\d+)', r'"usdPrice"\s*:\s*(\d+)']:
        m = re.search(p, html)
        if m:
            return int(m.group(1))

    return None


def _extract_auto_id(html: str, vehicle: Dict[str, Any]) -> Optional[int]:
    m = re.search(r'"autoId"\s*:\s*(\d+)', html)
    if m:
        return int(m.group(1))

    vid = vehicle.get("@id") or vehicle.get("url")
    if isinstance(vid, str):
        m2 = re.search(r'_(\d+)\.html', vid)
        if m2:
            return int(m2.group(1))

    return None


def _extract_expires_hash(html: str) -> tuple[Optional[str], Optional[str]]:
    """
    Достаём expires/hash для вызова:
      /users/phones/{auto_id}?expires=...&hash=...

    На AutoRia встречаются разные формы:
      - "expires":123456, "hash":"abcd..."
      - expires=123456&hash=abcd...
      - hash лежит в JSON как \"hash\":\"...\" (экранировано)
      - hash может быть без кавычек, рядом с expires
      - expires может называться expiresAt/expire/exp

    Возвращает (expires, hash) либо (None, None).
    """
    expires = None
    hash_ = None

    # 1) expires: разные ключи
    expires_patterns = [
        r'"expires"\s*:\s*(\d+)',
        r'\\?"expires\\?"\s*:\s*(\d+)',       # экранированный JSON внутри строки
        r'"expiresAt"\s*:\s*(\d+)',
        r'\\?"expiresAt\\?"\s*:\s*(\d+)',
        r'"expire"\s*:\s*(\d+)',
        r'\\?"expire\\?"\s*:\s*(\d+)',
        r'"exp"\s*:\s*(\d+)',
        r'\\?"exp\\?"\s*:\s*(\d+)',
    ]
    for pat in expires_patterns:
        m = re.search(pat, html)
        if m:
            expires = m.group(1)
            break

    # 2) hash/token/signature: разные ключи + экранированные формы
    hash_patterns = [
        r'"hash"\s*:\s*"([^"]+)"',
        r'\\?"hash\\?"\s*:\s*\\?"([^"\\]+)\\?"',     # \"hash\":\"...\"
        r'"token"\s*:\s*"([^"]+)"',
        r'\\?"token\\?"\s*:\s*\\?"([^"\\]+)\\?"',
        r'"signature"\s*:\s*"([^"]+)"',
        r'\\?"signature\\?"\s*:\s*\\?"([^"\\]+)\\?"',
        r'"sign"\s*:\s*"([^"]+)"',
        r'\\?"sign\\?"\s*:\s*\\?"([^"\\]+)\\?"',
        # иногда бывает без кавычек (редко)
        r'"hash"\s*:\s*([a-f0-9]{16,})',
        r'\\?"hash\\?"\s*:\s*([a-f0-9]{16,})',
    ]
    for pat in hash_patterns:
        m = re.search(pat, html, flags=re.I)
        if m:
            hash_ = m.group(1)
            break

    # 3) query-string форма (часто встречается прямо в ссылках/данных)
    if not expires or not hash_:
        m = re.search(
            r'(?:expires|expiresAt|expire|exp)=(\d+).*?(?:hash|token|signature|sign)=([a-f0-9]{16,})',
            html,
            flags=re.I
        )
        if m:
            expires = expires or m.group(1)
            hash_ = hash_ or m.group(2)

    # 4) финальная чистка (на случай мусора)
    if expires is not None and not expires.isdigit():
        expires = None
    if hash_ is not None:
        hash_ = hash_.strip()
        if len(hash_) < 10:
            hash_ = None

    return expires, hash_


async def _fetch_phone_number(
    client: httpx.AsyncClient,
    car_url: str,
    auto_id: int,
    expires: str,
    hash_: str,
) -> Optional[int]:
    """
    Рабочий эндпоинт:
    https://auto.ria.com/users/phones/{auto_id}?expires=...&hash=...
    """
    url = f"https://auto.ria.com/users/phones/{auto_id}?expires={expires}&hash={hash_}"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": car_url,
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
    }

    r = await client.get(url, headers=headers, timeout=20.0)
    if r.status_code != 200:
        return None

    try:
        data = r.json()
    except Exception:
        return None

    # варианты полей (бывает по-разному)
    raw = None
    if isinstance(data, dict):
        raw = (
            data.get("formattedPhoneNumber")
            or data.get("phoneNumber")
            or data.get("phone")
        )

    digits = _digits_only(str(raw or ""))
    if not digits:
        return None

    # нормализация UA
    if len(digits) == 10 and digits.startswith("0"):
        digits = "38" + digits

    if len(digits) < 10:
        return None

    return _safe_int(digits)


async def parse_card(client: httpx.AsyncClient, url: str, html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    vehicle = _pick_vehicle_jsonld(html)

    # title
    og_title = soup.select_one("meta[property='og:title']")
    title = (og_title.get("content") if og_title else None) or vehicle.get("name")

    # image_url
    og_image = soup.select_one("meta[property='og:image']")
    image_url = og_image.get("content") if og_image else None

    # images_count
    images_count = _extract_images_count(soup, vehicle, html)

    # odometer
    odometer = None
    mv = vehicle.get("mileageFromOdometer")
    if isinstance(mv, dict):
        odometer = _safe_int(mv.get("value"))

    # vin
    car_vin = vehicle.get("vehicleIdentificationNumber") or vehicle.get("vin")

    # car_number
    car_number = None
    text = soup.get_text(" ", strip=True)
    m = PLATE_RE.search(text)
    if m:
        car_number = m.group(0).strip()

    # username
    username = _extract_username(html)

    # price_usd
    price_usd = _extract_price_usd(vehicle, html)

    # phone_number (через expires/hash)
    phone_number = None
    auto_id = _extract_auto_id(html, vehicle)
    expires, hash_ = _extract_expires_hash(html)
    if auto_id and expires and hash_:
        phone_number = await _fetch_phone_number(client, url, auto_id, expires, hash_)

    return {
        "title": title,
        "price_usd": price_usd,
        "odometer": odometer,
        "username": username,
        "phone_number": phone_number,
        "image_url": image_url,
        "images_count": images_count,
        "car_number": car_number,
        "car_vin": car_vin,
    }
