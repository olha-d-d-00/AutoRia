from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CarListing


async def save_car(session: AsyncSession, url: str, **data):
    stmt = insert(CarListing).values(url=url, **data)
    stmt = stmt.on_conflict_do_update(
        index_elements=["url"],
        set_=data
    )
    await session.execute(stmt)
    await session.commit()
