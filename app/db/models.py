from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, BigInteger, DateTime, func, UniqueConstraint

class Base(DeclarativeBase):
    pass

class CarListing(Base):
    __tablename__ = "car_listings"
    __table_args__ = (UniqueConstraint("url", name="uq_car_listings_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    price_usd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    odometer: Mapped[int | None] = mapped_column(Integer, nullable=True)

    username: Mapped[str | None] = mapped_column(String, nullable=True)
    phone_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    images_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    car_number: Mapped[str | None] = mapped_column(String, nullable=True)
    car_vin: Mapped[str | None] = mapped_column(String, nullable=True)

    datetime_found: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)