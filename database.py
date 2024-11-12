from sqlalchemy import create_engine, BigInteger, Date, DateTime, ForeignKey, select
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.orm import sessionmaker
from datetime import datetime, date, time
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.associationproxy import AssociationProxy
from typing import List

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime)

    sections: Mapped[List["Section"]] = relationship(back_populates="user", uselist=True)
    currencies: Mapped[List["Currency"]] = relationship(back_populates="user", uselist=True)


class Section(Base):
    __tablename__ = "section"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    user_id = mapped_column(ForeignKey("user.id"))

    user: Mapped["User"] = relationship(back_populates="sections")
    sn: Mapped[List["SectionName"]] = relationship(cascade="all, delete-orphan", uselist=True)
    #relationship(back_populates="name", uselist=True)
    records: Mapped[List["Record"]] = relationship(back_populates="section")

    names: AssociationProxy[List[str]] = association_proxy("sn", "name")


class SectionName(Base):
    __tablename__ = "section_name"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("section.id"))
    name: Mapped[str] = mapped_column()
    added_datetime: Mapped[datetime] = mapped_column(DateTime)

    section: Mapped["Section"] = relationship(back_populates="sn")


class Record(Base):
    __tablename__ = "record"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("section.id"))
    currency_id: Mapped[int] = mapped_column(ForeignKey("currency.id"))
    datetime: Mapped[datetime] = mapped_column(DateTime)
    amount: Mapped[float] = mapped_column()
    added_datetime: Mapped[datetime] = mapped_column(DateTime)

    section: Mapped["Section"] = relationship(back_populates="records")
    currency: Mapped["Currency"] = relationship(back_populates="records")


class Currency(Base):
    __tablename__ = "currency"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("user.id"))

    user: Mapped["User"] = relationship(back_populates="currencies")
    cn: Mapped[List["CurrencyName"]] = relationship(cascade="all, delete-orphan", uselist=True)
    records: Mapped[List["Record"]] = relationship(back_populates="currency", uselist=True)

    names: AssociationProxy[List[str]] = association_proxy("cn", "name")


class CurrencyName(Base):
    __tablename__ = "currency_name"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    currency_id: Mapped[int] = mapped_column(ForeignKey("currency.id"))
    name: Mapped[str] = mapped_column()
    added_datetime: Mapped[datetime] = mapped_column(DateTime)

    currency: Mapped["Currency"] = relationship(back_populates="cn")


engine = create_engine(url="sqlite:///data.db", echo=True)
Base.metadata.create_all(engine)
with Session(engine) as session:
    print(session.query(Section).filter(Section.user_id == 515146433))
