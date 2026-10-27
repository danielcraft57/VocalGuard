"""Tests import prospect_phones depuis XLSX."""

from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base, ProspectPhone
from backend.services.prospect_phone_import_service import ProspectPhoneImportService


def _sample_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(
        [
            "name",
            "website",
            "category",
            "phone_number",
            "country",
            "address_1",
            "address_2",
            "longitude",
            "latitude",
            "rating",
            "reviews_count",
            "category_translate",
        ]
    )
    ws.append(
        [
            "Cafe Test",
            None,
            "food",
            "+33 3 83 11 22 33",
            "France",
            "1 rue Test",
            "54000 Nancy",
            6.1,
            48.6,
            4.5,
            10,
            "Restaurant, Bar",
        ]
    )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_import_prospect_phone_normalizes_categories(db_session):
    """Import une ligne sans site et cree categories M2M."""
    service = ProspectPhoneImportService(db_session)
    stats = service.import_xlsx(_sample_xlsx_bytes(), original_filename="Nancy.xlsx")
    assert stats.imported_rows == 1
    assert stats.source_city == "Nancy"

    row = db_session.query(ProspectPhone).one()
    assert row.name == "Cafe Test"
    assert row.phone_digits == "0383112233"
    assert row.postal_code == "54000"
    assert row.source_city == "Nancy"
    assert {c.name for c in row.categories} == {"Restaurant", "Bar"}


def test_import_skips_duplicate_phone(db_session):
    """Le meme numero est ignore au second import."""
    service = ProspectPhoneImportService(db_session)
    data = _sample_xlsx_bytes()
    first = service.import_xlsx(data, original_filename="Nancy.xlsx")
    second = service.import_xlsx(data, original_filename="Nancy.xlsx")
    assert first.imported_rows == 1
    assert second.imported_rows == 0
    assert second.skipped_duplicates == 1
