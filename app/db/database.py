from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.settings import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
