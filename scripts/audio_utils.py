"""
Utilitaires audio pour IVR / modem (Conexant).
Export WAV 8 kHz, mono, 8-bit pour compatibilite modem voix (callattendant, VocalGuard).
"""

from pathlib import Path
from typing import TYPE_CHECKING, Mapping

_INFO_MAX_FIELD = 2000

if TYPE_CHECKING:
    from pydub import AudioSegment


def export_wav_8k_8bit(segment: "AudioSegment", out_path: Path) -> None:
    """
    Exporte un AudioSegment en WAV 8 kHz, mono, 8-bit non signe.
    Format attendu par le modem Conexant (mode voix serie) et IVR telephone.

    Args:
        segment: Segment pydub (peut etre 16-bit, autre rate).
        out_path: Fichier WAV de sortie.
    """
    segment = segment.set_frame_rate(8000).set_channels(1)
    raw = segment.raw_data
    # 16-bit LE -> 8-bit unsigned (128 = silence)
    samples_8 = []
    for i in range(0, len(raw), 2):
        s16 = int.from_bytes(raw[i : i + 2], "little", signed=True)
        u8 = max(0, min(255, (s16 >> 8) + 128))
        samples_8.append(u8)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import wave
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(1)
        wf.setframerate(8000)
        wf.writeframes(bytes(samples_8))


def _riff_serialize_chunk(chunk_id: bytes, chunk_data: bytes) -> bytes:
    if len(chunk_id) != 4:
        raise ValueError("chunk_id doit faire 4 octets")
    pad = len(chunk_data) & 1
    return chunk_id + len(chunk_data).to_bytes(4, "little") + chunk_data + (b"\x00" if pad else b"")


def _riff_read_wave_chunks(blob: bytes) -> list[tuple[bytes, bytes]]:
    """Lit les sous-chunks après l’identifiant WAVE (fmt, data, …)."""
    if len(blob) < 12 or blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        raise ValueError("fichier WAV RIFF attendu")
    pos = 12
    out: list[tuple[bytes, bytes]] = []
    while pos + 8 <= len(blob):
        cid = blob[pos : pos + 4]
        sz = int.from_bytes(blob[pos + 4 : pos + 8], "little")
        pos += 8
        if pos + sz > len(blob):
            raise ValueError("chunk WAV tronqué")
        cdata = blob[pos : pos + sz]
        pos += sz
        if sz & 1:
            pos += 1
        out.append((cid, cdata))
    return out


def _riff_build_list_info_body(fields: Mapping[str, str]) -> bytes:
    """Corps du chunk LIST (commence par INFO + sous-chunks INAM, IART, …)."""
    body = b"INFO"
    for key, val in fields.items():
        if len(key) != 4:
            continue
        kid = key.encode("ascii", errors="ignore")
        if len(kid) != 4:
            continue
        # CP1252 : mieux reconnu par l’Explorateur Windows pour LIST/INFO que l’UTF-8 brut.
        raw = (val or "")[:_INFO_MAX_FIELD].encode("cp1252", errors="replace") + b"\x00"
        if len(raw) & 1:
            raw += b"\x00"
        body += kid + len(raw).to_bytes(4, "little") + raw
    return body


def apply_wav_riff_info_tags(
    wav_path: Path,
    *,
    title: str = "",
    subtitle: str = "",
    artist: str = "",
    album: str = "",
    year: str = "",
    track_number: str = "",
    genre: str = "",
    media_origin: str = "",
    copyright_text: str = "",
    parental_control: str = "",
    parental_control_reason: str = "",
    comment: str = "",
    software: str = "VocalGuard",
) -> None:
    """
    Injecte un chunk RIFF LIST/INFO (INAM, IART, IPRD, …) pour l’affichage dans l’Explorateur Windows.

    Réécrit le fichier en plaçant LIST/INFO **après** le chunk ``data`` (meilleure compatibilité Explorateur).
    Supprime un LIST existant pour éviter les doublons.
    """
    fields: dict[str, str] = {}
    if title.strip():
        fields["INAM"] = title.strip()
    if subtitle.strip():
        # "Subject": pratique comme sous-titre dans LIST/INFO.
        fields["ISBJ"] = subtitle.strip()
    if artist.strip():
        fields["IART"] = artist.strip()
    if album.strip():
        fields["IPRD"] = album.strip()
    if year.strip():
        fields["ICRD"] = year.strip()
    if track_number.strip():
        # ITRK est non standard mais largement utilisé pour le n° de piste.
        fields["ITRK"] = track_number.strip()
    if genre.strip():
        fields["IGNR"] = genre.strip()
    if media_origin.strip():
        # Source/origine média.
        fields["ISRC"] = media_origin.strip()
    if copyright_text.strip():
        fields["ICOP"] = copyright_text.strip()

    parental = parental_control.strip().lower()
    parental_reason = parental_control_reason.strip()
    parental_tokens: list[str] = []
    if parental:
        parental_tokens.append(f"parental_control={parental}")
    if parental_reason:
        parental_tokens.append(f"parental_reason={parental_reason}")
    if parental_tokens:
        # Champ mots-clés : facile à lire/filtrer même si l'explorateur ne l'affiche pas.
        fields["IKEY"] = " ; ".join(parental_tokens)[:_INFO_MAX_FIELD]

    if comment.strip():
        fields["ICMT"] = comment.strip()[:_INFO_MAX_FIELD]
    if software.strip():
        fields["ISFT"] = software.strip()
    if not fields:
        return

    blob = wav_path.read_bytes()
    chunks = _riff_read_wave_chunks(blob)
    chunks = [c for c in chunks if c[0] != b"LIST"]
    list_chunk = _riff_serialize_chunk(b"LIST", _riff_build_list_info_body(fields))

    new_parts: list[bytes] = []
    inserted = False
    for cid, cdata in chunks:
        new_parts.append(_riff_serialize_chunk(cid, cdata))
        if cid == b"data" and not inserted:
            new_parts.append(list_chunk)
            inserted = True
    if not inserted:
        new_parts.append(list_chunk)

    wave_payload = b"WAVE" + b"".join(new_parts)
    wav_path.write_bytes(b"RIFF" + len(wave_payload).to_bytes(4, "little") + wave_payload)
