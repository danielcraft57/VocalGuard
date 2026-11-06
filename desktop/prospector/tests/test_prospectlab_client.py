"""Tests client ProspectLab (mock HTTP)."""

from __future__ import annotations

import httpx
import pytest

from desktop.prospector.prospectlab_client import ProspectLabClient


def test_list_groupes_parsing():
    """Parse liste groupes."""
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json=[{"id": 1, "nom": "Camp A", "entreprises_count": 3}],
        )
    )
    client = ProspectLabClient(
        base_url="http://test/api/public",
        token="tok",
    )
    with httpx.Client(transport=transport) as _:
        pass

    real = ProspectLabClient(base_url="http://test/api/public", token="tok")
    real._request = lambda method, path, **kw: [{"id": 1, "nom": "Camp A", "entreprises_count": 3}]  # type: ignore
    rows = real.list_groupes()
    assert rows[0]["nom"] == "Camp A"


def test_iter_groupe_entreprises_pages():
    """Pagination groupe entreprises."""
    client = ProspectLabClient(base_url="http://x/api/public", token="t")
    pages = [
        {"items": [{"id": 1, "raison_sociale": "A"}], "total": 2},
        {"items": [{"id": 2, "raison_sociale": "B"}], "total": 2},
    ]
    calls = {"n": 0}

    def fake_list(gid, **params):
        i = calls["n"]
        calls["n"] += 1
        return pages[min(i, len(pages) - 1)]

    client.list_groupe_entreprises = fake_list  # type: ignore
    items = list(client.iter_groupe_entreprises(5, limit=1))
    assert len(items) == 2
