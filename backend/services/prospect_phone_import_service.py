"""
Import Excel ProspectLab vers la table normalisee prospect_phones.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from loguru import logger
from openpyxl import load_workbook
from sqlalchemy import delete as sa_delete
from sqlalchemy.orm import Session

from backend.database.models import (
    ProspectPhone,
    ProspectPhoneCategory,
    ProspectPhoneGoogleType,
    ProspectPhoneImportBatch,
    prospect_phone_category_links,
    prospect_phone_google_type_links,
)
from backend.services.entreprise_import_service import (
    EntrepriseImportService,
    _as_str,
    _float_or_none,
    _int_or_none,
    _normalize_header,
    _phone_digits,
    _slugify,
    _split_categories,
)

_POSTAL_RE = re.compile(r"\b(\d{5})\b")


@dataclass(frozen=True)
class ProspectPhoneImportStats:
    """Resume d'un import vers prospect_phones."""

    batch_id: int
    original_filename: Optional[str]
    source_city: Optional[str]
    total_rows: int
    imported_rows: int
    skipped_with_website: int
    skipped_invalid: int
    skipped_duplicates: int


def source_city_from_filename(original_filename: Optional[str]) -> Optional[str]:
    """
    Deduit la ville source depuis le nom de fichier (ex. Nancy.xlsx -> Nancy).

    @param original_filename Nom du fichier uploadé.
    @returns Libelle ville ou None.
    """
    if not original_filename:
        return None
    stem = Path(original_filename).stem.strip()
    return stem or None


def _extract_postal_code(*address_parts: Optional[str]) -> Optional[str]:
    """Extrait un code postal FR (5 chiffres) depuis les lignes d'adresse."""
    for part in address_parts:
        if not part:
            continue
        m = _POSTAL_RE.search(part)
        if m:
            return m.group(1)
    return None


class ProspectPhoneImportService:
    """
    Service d'import XLSX vers prospect_phones.

    Reutilise le parseur de colonnes de EntrepriseImportService (alias headers).
    """

    def __init__(self, db: Session) -> None:
        self._db = db
        self._row_parser = EntrepriseImportService(db)

    def import_xlsx(
        self,
        xlsx_bytes: bytes,
        original_filename: Optional[str] = None,
        source: str = "excel",
        batch_id: Optional[int] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> ProspectPhoneImportStats:
        """
        Importe un classeur et renvoie les compteurs.

        @param xlsx_bytes Contenu binaire du fichier.
        @param original_filename Nom source (ville deduite du stem).
        @param source Tag technique (excel, directory).
        @param batch_id Batch existant (import async) ou None pour en creer un.
        @param progress_callback Heartbeat optionnel (current, imported_rows, ...).
        @returns Statistiques d'import.
        """
        source_city = source_city_from_filename(original_filename)

        if batch_id is not None:
            batch = self._db.get(ProspectPhoneImportBatch, batch_id)
            if batch is None:
                raise ValueError(f"Batch introuvable: {batch_id}")
            batch.phase = "import"
            if original_filename:
                batch.original_filename = original_filename
            if source_city:
                batch.source_city = source_city
            self._db.commit()
        else:
            batch = ProspectPhoneImportBatch(
                original_filename=original_filename,
                source_city=source_city,
                source=source,
                phase="import",
            )
            self._db.add(batch)
            self._db.commit()
            self._db.refresh(batch)

        wb = load_workbook(filename=BytesIO(xlsx_bytes), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            return ProspectPhoneImportStats(
                batch_id=batch.id,
                original_filename=original_filename,
                source_city=source_city,
                total_rows=0,
                imported_rows=0,
                skipped_with_website=0,
                skipped_invalid=0,
                skipped_duplicates=0,
            )

        header_to_index: Dict[str, int] = {}
        for idx, cell in enumerate(header_row):
            key = _normalize_header(cell)
            if key:
                header_to_index[key] = idx

        col_index = self._row_parser._resolve_columns(header_to_index)
        logger.info("Import prospect_phones: colonnes resolues={}", col_index)

        try:
            batch.total_rows = max(0, int(getattr(ws, "max_row", 1)) - 1)
            self._db.commit()
        except Exception:
            pass

        seen_signatures: set[Tuple[str, str]] = set()
        total_rows = 0

        for excel_row_number, row_values in enumerate(rows_iter, start=2):
            total_rows += 1
            normalized = self._row_parser._row_to_record(row_values, col_index)

            name = normalized.get("name")
            website = normalized.get("website")
            phone = normalized.get("phone_number")

            if not name:
                batch.skipped_invalid += 1
                self._maybe_progress(batch, total_rows, progress_callback)
                continue

            if website:
                batch.skipped_with_website += 1
                self._maybe_progress(batch, total_rows, progress_callback)
                continue

            digits = _phone_digits(phone) or ""
            if not digits:
                batch.skipped_invalid += 1
                self._maybe_progress(batch, total_rows, progress_callback)
                continue

            sig = ("phone", digits)
            if sig in seen_signatures:
                batch.skipped_duplicates += 1
                self._maybe_progress(batch, total_rows, progress_callback)
                continue
            seen_signatures.add(sig)

            existing = (
                self._db.query(ProspectPhone)
                .filter(ProspectPhone.phone_digits == digits)
                .one_or_none()
            )
            if existing is not None:
                batch.skipped_duplicates += 1
                self._maybe_progress(batch, total_rows, progress_callback)
                continue

            city = normalized.get("city")
            if not city and source_city:
                city = source_city

            postal = _extract_postal_code(normalized.get("address_2"), normalized.get("address_1"))
            google_raw = _as_str(normalized.get("category"))
            translate_raw = _as_str(normalized.get("category_translate"))

            prospect = ProspectPhone(
                import_batch_id=batch.id,
                name=name.strip(),
                phone_number=phone,
                phone_digits=digits,
                source_city=source_city,
                country=normalized.get("country"),
                city=city,
                postal_code=postal,
                address_1=normalized.get("address_1"),
                address_2=normalized.get("address_2"),
                longitude=_float_or_none(normalized.get("longitude")),
                latitude=_float_or_none(normalized.get("latitude")),
                rating=_float_or_none(normalized.get("rating")),
                reviews_count=_int_or_none(normalized.get("reviews_count")),
                website=None,
                google_categories_raw=google_raw,
                category_translate_raw=translate_raw,
                verification_status="pending",
                osint_status="pending",
                prospectlab_status="pending",
            )
            self._db.add(prospect)
            self._db.flush()

            self._db.execute(
                sa_delete(prospect_phone_category_links).where(
                    prospect_phone_category_links.c.prospect_phone_id == prospect.id
                )
            )
            linked_ids: set[int] = set()
            for category_name in _split_categories(normalized.get("category_translate")):
                cat = self._get_or_create_category(category_name)
                if cat.id in linked_ids:
                    continue
                linked_ids.add(cat.id)
                prospect.categories.add(cat)

            self._db.execute(
                sa_delete(prospect_phone_google_type_links).where(
                    prospect_phone_google_type_links.c.prospect_phone_id == prospect.id
                )
            )
            linked_gt: set[int] = set()
            for gtype in _split_categories(google_raw):
                gt = self._get_or_create_google_type(gtype)
                if gt.id in linked_gt:
                    continue
                linked_gt.add(gt.id)
                prospect.google_types.add(gt)

            batch.imported_rows += 1
            if total_rows % 100 == 0:
                self._db.commit()

            self._maybe_progress(batch, total_rows, progress_callback)

        self._db.commit()
        self._db.refresh(batch)

        return ProspectPhoneImportStats(
            batch_id=batch.id,
            original_filename=batch.original_filename,
            source_city=batch.source_city,
            total_rows=batch.total_rows,
            imported_rows=batch.imported_rows,
            skipped_with_website=batch.skipped_with_website,
            skipped_invalid=batch.skipped_invalid,
            skipped_duplicates=batch.skipped_duplicates,
        )

    def import_directory(self, directory: Path) -> List[ProspectPhoneImportStats]:
        """
        Importe tous les .xlsx d'un dossier (un batch par fichier).

        @param directory Chemin absolu vers le dossier ProspectLab.
        @returns Liste des resumes par fichier.
        """
        if not directory.is_dir():
            raise ValueError(f"Dossier introuvable: {directory}")
        results: List[ProspectPhoneImportStats] = []
        for path in sorted(directory.glob("*.xlsx")):
            data = path.read_bytes()
            stats = self.import_xlsx(
                xlsx_bytes=data,
                original_filename=path.name,
                source="directory",
            )
            results.append(stats)
            logger.info(
                "Import {}: {} lignes importees / {}",
                path.name,
                stats.imported_rows,
                stats.total_rows,
            )
        return results

    def _get_or_create_google_type(self, raw_type: str) -> ProspectPhoneGoogleType:
        label = raw_type.strip()
        code = _slugify(label.replace("_", " "))
        row = (
            self._db.query(ProspectPhoneGoogleType)
            .filter(ProspectPhoneGoogleType.code == code)
            .one_or_none()
        )
        if row is not None:
            return row
        created = ProspectPhoneGoogleType(code=code, label=label)
        self._db.add(created)
        self._db.flush()
        return created

    def _get_or_create_category(self, category_name: str) -> ProspectPhoneCategory:
        normalized = category_name.strip()
        slug = _slugify(normalized)
        row = (
            self._db.query(ProspectPhoneCategory)
            .filter(ProspectPhoneCategory.slug == slug)
            .one_or_none()
        )
        if row is not None:
            return row
        created = ProspectPhoneCategory(name=normalized, slug=slug)
        self._db.add(created)
        self._db.flush()
        return created

    def _maybe_progress(
        self,
        batch: ProspectPhoneImportBatch,
        current: int,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    ) -> None:
        if progress_callback and (current == 1 or current % 25 == 0):
            try:
                progress_callback(
                    {
                        "batch_id": batch.id,
                        "current": current,
                        "imported_rows": batch.imported_rows,
                        "skipped_with_website": batch.skipped_with_website,
                        "skipped_invalid": batch.skipped_invalid,
                        "skipped_duplicates": batch.skipped_duplicates,
                        "total_rows": batch.total_rows,
                    }
                )
            except Exception:
                pass
