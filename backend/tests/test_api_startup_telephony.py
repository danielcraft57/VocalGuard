"""Startup API sans CallManager quand le daemon telephonie est actif."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.config import Config


@pytest.mark.asyncio
async def test_api_startup_skips_call_manager_with_telephony_daemon() -> None:
    """USE_TELEPHONY_DAEMON=1 : pas de modem/STT/TTS sur le processus API."""
    cfg = Config()
    cfg.use_telephony_daemon = True
    cfg.telephony_daemon_url = "http://127.0.0.1:8090"

    with patch("backend.api.app.db_module.init_database", new_callable=AsyncMock):
        with patch("backend.api.app.httpx.AsyncClient") as httpx_cls:
            client = httpx_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(return_value=MagicMock(status_code=200))
            with patch("backend.api.app.CallManager") as cm_cls:
                from backend.api.app import create_app

                app = create_app(cfg)
                for handler in app.router.on_startup:
                    await handler()

                cm_cls.assert_not_called()
                assert app.state.call_manager is None
