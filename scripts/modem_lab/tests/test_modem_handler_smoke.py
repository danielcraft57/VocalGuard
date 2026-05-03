"""
Tests légers ModemHandler sans matériel (logique métier isolée).

Nécessite la racine VocalGuard dans sys.path pour importer backend.*
"""

import asyncio
import sys
import unittest
from pathlib import Path

_VOCALGUARD_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_VOCALGUARD_ROOT))

from backend.core.modem_handler import (  # noqa: E402
    ModemHandler,
    _response_has_numeric_at_result,
    _serial_buffer_shows_remote_pickup,
    _vrx_stream_contains_hangup_marker,
)
from backend.core.telephony_events import (  # noqa: E402
    count_dle_ring_markers,
    outbound_wait_status_summary,
    remote_pickup_likely_detail,
)


class ModemHandlerSmokeTests(unittest.TestCase):
    def test_dial_number_numero_vide(self) -> None:
        m = ModemHandler("COM_DUMMY", 115200)
        ok, msg = asyncio.run(m.dial_number(""))
        self.assertFalse(ok)
        self.assertEqual(msg, "numero vide")

    def test_normalize_phone_for_command_strip_separateurs(self) -> None:
        m = ModemHandler("COM_DUMMY", 115200)
        self.assertEqual(
            m._normalize_phone_for_command(" 078 083-3873 "),
            "0780833873",
        )

    def test_normalize_plus33_vers_national_fr(self) -> None:
        m = ModemHandler("COM_DUMMY", 115200)
        self.assertEqual(
            m._normalize_phone_for_command("+33 7 80 83 38 73"),
            "0780833873",
        )

    def test_send_dtmf_digit_invalides(self) -> None:
        m = ModemHandler("COM_DUMMY", 115200)

        async def run() -> None:
            self.assertFalse(await m.send_dtmf(""))
            self.assertFalse(await m.send_dtmf("z"))
            self.assertFalse(await m.send_dtmf("EE"))

        asyncio.run(run())

    def test_supports_voice_serial_quand_non_init(self) -> None:
        m = ModemHandler("COM_DUMMY", 115200)
        self.assertFalse(m.supports_voice_serial)

    def test_parse_caller_id(self) -> None:
        m = ModemHandler(None, 115200)
        raw = b"RING\r\nNMBR=0780833873\r\nNAME=DANIEL\r\n"
        nid, nom = m._parse_caller_id_from_response(raw)
        self.assertEqual(nid, "0780833873")
        self.assertEqual(nom, "DANIEL")


class RemotePickupBufferTests(unittest.TestCase):
    def test_dle_a(self) -> None:
        self.assertTrue(_serial_buffer_shows_remote_pickup(b"foo\x10a"))

    def test_vcon(self) -> None:
        self.assertTrue(_serial_buffer_shows_remote_pickup(b"\r\nVCON\r\n"))

    def test_negatif_silence(self) -> None:
        self.assertFalse(_serial_buffer_shows_remote_pickup(bytes([128]) * 100))


class OutboundWaitLogSummaryTests(unittest.TestCase):
    """Aligné sur les logs `wait_voice_outbound_answer` : DLE+R cumulés, ligne de synthèse décrochage."""

    def test_compte_sonneries_dle_r(self) -> None:
        # Trois indications sonnerie puis réponse (cf. modem qui répète DLE+R par cycle)
        flux = b"\x10R\x10R\x10R\x10a"
        self.assertEqual(count_dle_ring_markers(flux), 3)
        ok, why = remote_pickup_likely_detail(flux)
        self.assertTrue(ok)
        self.assertIn("DLE+a", why)

    def test_resume_tampon_style_log(self) -> None:
        self.assertEqual(
            outbound_wait_status_summary(b"\x10R\x10b"),
            "DLE+R=1|occupe=1",
        )
        s = outbound_wait_status_summary(b"VCON\r\n")
        self.assertIn("DLE+R=0", s)
        self.assertIn("decrochage=VCON", s.replace(" ", "_"))

    def test_decrochage_apres_sonneries_connect_num(self) -> None:
        flux = b"\x10R\x10R\r\n1\r\n"
        self.assertEqual(count_dle_ring_markers(flux), 2)
        ok, why = remote_pickup_likely_detail(flux)
        self.assertTrue(ok)
        self.assertIn("numerique", why)


class NumericAtResultTests(unittest.TestCase):
    def test_connect_chiffre_1(self) -> None:
        self.assertTrue(_response_has_numeric_at_result(b"\r\n1\r\n", (1,)))

    def test_busy_chiffre_7(self) -> None:
        self.assertTrue(_response_has_numeric_at_result(b"foo\n7\n", (7,)))

    def test_pas_de_faux_14_pour_1(self) -> None:
        self.assertFalse(_response_has_numeric_at_result(b"\r\n14\r\n", (1,)))


class VrxHangupMarkerTests(unittest.TestCase):
    def test_detecte_no_carrier(self) -> None:
        self.assertTrue(_vrx_stream_contains_hangup_marker(b"PCM...\r\nNO CARRIER\r\n"))

    def test_detecte_no_answer_insensible_casse(self) -> None:
        self.assertTrue(_vrx_stream_contains_hangup_marker(b"trailer no answer "))

    def test_pas_de_faux_positif_silence_pcm(self) -> None:
        self.assertFalse(_vrx_stream_contains_hangup_marker(bytes([128]) * 512))


if __name__ == "__main__":
    unittest.main()
