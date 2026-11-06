"""Tests campaign_store import / match."""

from __future__ import annotations

from desktop.prospector.campaign_store import CampaignStore
from desktop.prospector.db.models import PlEntreprise, PlGroupe, PlPhone


def test_find_entreprise_by_phone(prospector_db):
    """Match phone_digits."""
    ent = PlEntreprise(prospectlab_id=100, raison_sociale="ACME")
    prospector_db.add(ent)
    prospector_db.flush()
    prospector_db.add(
        PlPhone(
            entreprise_id=ent.id,
            phone_raw="03 83 11 22 33",
            phone_digits="0383112233",
            is_primary=True,
        )
    )
    prospector_db.commit()
    store = CampaignStore(prospector_db)
    found = store.find_entreprise_by_phone("+33 3 83 11 22 33")
    assert found is not None
    assert found.raison_sociale == "ACME"


def test_import_groupe_mock(prospector_db):
    """Import via client mock."""
    g = PlGroupe(prospectlab_id=7, nom="G7", entreprises_count=1)
    prospector_db.add(g)
    prospector_db.commit()

    class FakeClient:
        def get_groupe(self, gid):
            return {"id": gid, "nom": "G7"}

        def iter_groupe_entreprises(self, gid, **filters):
            yield {
                "id": 501,
                "raison_sociale": "Dupont",
                "telephone": "0612345678",
                "ville": "Nancy",
            }

    store = CampaignStore(prospector_db)
    batch = store.import_groupe_entreprises(7, FakeClient(), filters={"has_phone": 1})
    assert batch.row_count == 1
    qi = store.next_queue_item()
    assert qi is not None
    assert qi.entreprise.raison_sociale == "Dupont"
