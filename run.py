import asyncio

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import text

from app.crawler.parser import parse_card
from app.crawler.scraper import get_html, scrape_list_pages
from app.crawler.phone_playwright import get_phone_via_playwright
from app.db.crud import save_car
from app.db.database import AsyncSessionLocal, engine
from app.db.models import Base
from app.jobs import dump_db
from app.settings import DUMP_TIME, SCRAPE_TIME, TZ


def _hhmm_to_cron(time_str: str) -> tuple[int, int]:
    hh, mm = time_str.strip().split(":")
    return int(hh), int(mm)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        res = await conn.execute(text("SELECT 1"))
        print("DB OK:", res.scalar_one())


async def scrape_job(limit_pages: int | None = 1):
    urls = await scrape_list_pages(limit_pages=limit_pages)

    with_phone = 0
    without_phone = 0
    errors = 0

    async with AsyncSessionLocal() as session:
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
            timeout=httpx.Timeout(20.0, connect=10.0),
        ) as client:
            for url in urls:
                try:
                    html = await get_html(client, url)
                    data = await parse_card(client, url, html)

                    # --- fallback через Playwright ---
                    if not data.get("phone_number"):
                        phone = await get_phone_via_playwright(url)
                        if phone:
                            data["phone_number"] = phone
                            with_phone += 1
                            print(f"[phone via playwright] {url}")
                        else:
                            without_phone += 1
                            print(f"[no phone] {url}")
                    else:
                        with_phone += 1

                    await save_car(session, url=url, **data)
                    print(f"[scraped] {url}")

                except Exception as e:
                    errors += 1
                    print(f"[error] {url} -> {e}")

    print(
        f"SUMMARY: with_phone={with_phone} "
        f"without_phone={without_phone} "
        f"errors={errors}"
    )


def start_scheduler():
    scheduler = AsyncIOScheduler(timezone=TZ)

    # ---- dump job ----
    dump_h, dump_m = _hhmm_to_cron(DUMP_TIME)
    scheduler.add_job(
        dump_db,
        CronTrigger(hour=dump_h, minute=dump_m, timezone=TZ),
        id="dump_db",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # ---- scrape job ----
    scrape_h, scrape_m = _hhmm_to_cron(SCRAPE_TIME)

    def schedule_scrape():
        asyncio.create_task(scrape_job(limit_pages=None))

    scheduler.add_job(
        schedule_scrape,
        CronTrigger(hour=scrape_h, minute=scrape_m, timezone=TZ),
        id="scrape_job",
        replace_existing=True,
        misfire_grace_time=60,
    )

    scheduler.start()
    print(
        f"Scheduler started. TZ={TZ}, "
        f"SCRAPE_TIME={SCRAPE_TIME}, "
        f"DUMP_TIME={DUMP_TIME}"
    )


async def main():
    await init_db()
    start_scheduler()
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
