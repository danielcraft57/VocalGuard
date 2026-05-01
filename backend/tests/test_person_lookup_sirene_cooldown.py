import time

import pytest

from backend.services.person_lookup import PersonLookupService


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    calls = 0

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, *args, **kwargs):
        _FakeAsyncClient.calls += 1
        return _FakeResponse(status_code=401, text='{"message":"Unauthorized"}')


@pytest.mark.asyncio
async def test_sirene_401_enables_cooldown(monkeypatch) -> None:
    import backend.services.person_lookup as person_lookup_module

    monkeypatch.setattr(person_lookup_module.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.calls = 0
    PersonLookupService._sirene_disabled_until = 0.0
    PersonLookupService._sirene_auth_warned = False

    service = PersonLookupService()
    service.sirene_api_key = "fake-key"

    await service._query_sirene("+33601020304")
    first_calls = _FakeAsyncClient.calls
    assert first_calls == 1
    assert PersonLookupService._sirene_disabled_until > time.monotonic()

    # La deuxième requête est court-circuitée pendant la fenêtre de cooldown.
    await service._query_sirene("+33601020304")
    assert _FakeAsyncClient.calls == first_calls
