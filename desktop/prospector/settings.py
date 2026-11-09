"""
Configuration Prospector (prospector.env + variables d'environnement).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def repo_root() -> Path:
    """Racine du depot VocalGuard."""
    return Path(__file__).resolve().parents[2]


def exe_dir() -> Path:
    """Dossier exe PyInstaller ou racine repo."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return repo_root()


def bundle_root() -> Path:
    """
    Racine des donnees applicatives (depot en dev, _MEIPASS ou _internal en exe).

    @returns Chemin utilise pour alembic.ini et config livres avec PyInstaller.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        internal = exe_dir() / "_internal"
        if internal.is_dir():
            return internal
        return exe_dir()
    return repo_root()


def default_db_path() -> Path:
    """
    Fichier SQLite utilisateur par defaut.

    @returns Chemin prospector.db sous Documents.
    """
    docs = Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / "Documents"
    return docs / "VocalGuard" / "prospector" / "prospector.db"


DEFAULT_PROSPECTLAB_URL = "http://node15.lan:5000"


def normalize_prospectlab_url(url: str) -> str:
    """
    Base ProspectLab sans suffixe /api/public.

    @param url URL saisie ou lue depuis prospector.env.
    @returns URL normalisee ou chaine vide.
    """
    u = (url or "").strip().rstrip("/")
    if u.lower().endswith("/api/public"):
        u = u[: -len("/api/public")].rstrip("/")
    return u


def prospector_env_path() -> Path:
    """
    Fichier prospector.env (priorite dossier exe, puis racine repo).

    @returns Chemin cible lecture/ecriture.
    """
    exe_side = exe_dir() / "prospector.env"
    if exe_side.is_file():
        return exe_side
    for side in (repo_root() / "prospector.env", repo_root() / "desktop" / "prospector.env"):
        if side.is_file():
            return side
    return exe_side


def ensure_prospector_env_file() -> Path | None:
    """
    Cree prospector.env depuis l'exemple si absent (surtout en exe PyInstaller).

    @returns Chemin cree ou None.
    """
    target = exe_dir() / "prospector.env"
    if target.is_file():
        return target
    if not getattr(sys, "frozen", False):
        return None
    for candidate in (
        exe_dir() / "prospector.env.example",
        repo_root() / "desktop" / "prospector.env.example",
    ):
        if not candidate.is_file():
            continue
        target.write_text(candidate.read_text(encoding="utf-8"), encoding="utf-8")
        return target
    return None


def persist_prospector_env(updates: dict[str, str]) -> Path:
    """
    Met a jour prospector.env et os.environ (URL ProspectLab, token, COM, etc.).

    @param updates Cles/valeurs sans export.
    @returns Chemin ecrit.
    """
    path = prospector_env_path()
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    keyed: dict[str, str] = {}
    preserved: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            preserved.append(raw)
            continue
        parse = line
        if parse.lower().startswith("export "):
            parse = parse[7:].strip()
        key, val = parse.split("=", 1)
        keyed[key.strip()] = val.strip()
    for key, val in updates.items():
        if val is None:
            keyed.pop(key, None)
        else:
            keyed[key] = val
    out_lines = list(preserved)
    if not any("=" in ln for ln in out_lines):
        out_lines = ["# VocalGuard Prospector — ne pas committer avec un vrai token."]
    for key in sorted(keyed.keys()):
        out_lines.append(f"{key}={keyed[key]}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    for key, val in updates.items():
        if val is not None:
            os.environ[key] = val
    return path


def database_url() -> str:
    """
    URL SQLAlchemy pour la base locale.

    @returns sqlite:///...
    """
    explicit = (os.environ.get("VG_PROSPECTOR_DATABASE_URL") or "").strip()
    if explicit:
        return explicit
    db_path = (os.environ.get("VG_PROSPECTOR_DB") or "").strip()
    if db_path:
        p = Path(db_path)
    else:
        p = default_db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{p.as_posix()}"


def load_prospector_env() -> Path | None:
    """
    Charge prospector.env a cote de l'exe ou a la racine repo.

    @returns Chemin lu ou None.
    """
    ensure_prospector_env_file()
    candidates = (
        exe_dir() / "prospector.env",
        repo_root() / "prospector.env",
        repo_root() / "desktop" / "prospector.env",
    )
    for path in candidates:
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key == "PROSPECTLAB_URL":
                val = normalize_prospectlab_url(val)
            if key and key not in os.environ:
                os.environ[key] = val
        return path
    return None


def prospectlab_base_url() -> str:
    """Base URL API publique ProspectLab (sans /api/public)."""
    base = (os.environ.get("PROSPECTLAB_URL") or os.environ.get("VG_PROSPECTLAB_URL") or "").strip()
    return normalize_prospectlab_url(base)


def prospectlab_api_prefix() -> str:
    """Prefixe /api/public."""
    return f"{prospectlab_base_url()}/api/public" if prospectlab_base_url() else ""


def prospectlab_token() -> str:
    """Bearer token ProspectLab."""
    return (os.environ.get("PROSPECTLAB_TOKEN") or os.environ.get("VG_PROSPECTLAB_TOKEN") or "").strip()


def stt_http_url() -> str:
    """URL HTTP STT node15."""
    return (os.environ.get("VG_STT_URL") or "http://node15.lan:8100").strip().rstrip("/")


def stt_ws_url() -> str:
    """
    URL WebSocket transcription.

    @returns ws://.../ws/v1/transcribe
    """
    custom = (os.environ.get("VG_STT_WS") or "").strip()
    if custom:
        return custom
    http = stt_http_url()
    if http.startswith("https://"):
        return http.replace("https://", "wss://", 1) + "/ws/v1/transcribe"
    if http.startswith("http://"):
        return http.replace("http://", "ws://", 1) + "/ws/v1/transcribe"
    return "ws://node15.lan:8100/ws/v1/transcribe"


def stt_token() -> str:
    """Token STT interne."""
    return (os.environ.get("VG_STT_TOKEN") or os.environ.get("STT_INTERNAL_TOKEN") or "").strip()


def modem_com_port() -> str:
    """Port COM modem USB."""
    return (os.environ.get("VG_MODEM_COM") or os.environ.get("MODEM_PORT") or "").strip()


def modem_baudrate() -> int:
    """Baudrate modem."""
    raw = (os.environ.get("VG_MODEM_BAUD") or "230400").strip()
    try:
        return int(raw)
    except ValueError:
        return 230400


def call_line_gain() -> float:
    """
    Volume ecoute ligne -> casque pendant un appel (0.05..1).

    Priorite : ui_prefs.json, puis VG_PROSPECTOR_LINE_GAIN, puis VG_STUDIO_PLAY_GAIN.
    """
    try:
        from desktop.prospector.ui_prefs import load_prefs

        raw_pref = load_prefs().get("call_line_gain")
        if raw_pref is not None:
            return max(0.05, min(1.0, float(raw_pref)))
    except Exception:
        pass
    for key in ("VG_PROSPECTOR_LINE_GAIN", "VG_STUDIO_PLAY_GAIN"):
        val = (os.environ.get(key) or "").strip()
        if val:
            try:
                return max(0.05, min(1.0, float(val)))
            except ValueError:
                pass
    return 0.22


def call_mic_gain() -> float:
    """
    Gain micro montant vers la ligne (0.05..1.5).

    @returns Facteur PTT / uplink.
    """
    for key in ("VG_PROSPECTOR_MIC_GAIN", "VG_STUDIO_MIC_GAIN"):
        val = (os.environ.get(key) or "").strip()
        if val:
            try:
                return max(0.05, min(1.5, float(val)))
            except ValueError:
                pass
    return 0.85


def record_line_gain() -> float:
    """
    Gain ligne dans le WAV (distinct de l'ecoute casque temps reel).

    Le flux modem VRX est souvent proche du plein echelle : 0.32..0.45 conseille.
    """
    for key in ("VG_PROSPECTOR_RECORD_LINE_GAIN",):
        val = (os.environ.get(key) or "").strip()
        if val:
            try:
                return max(0.08, min(1.0, float(val)))
            except ValueError:
                pass
    try:
        from desktop.prospector.ui_prefs import load_prefs

        raw = load_prefs().get("record_line_gain")
        if raw is not None:
            return max(0.08, min(1.0, float(raw)))
    except Exception:
        pass
    return 0.30


def record_mic_gain() -> float:
    """Gain micro (canal R) dans le WAV."""
    for key in ("VG_PROSPECTOR_RECORD_MIC_GAIN",):
        val = (os.environ.get(key) or "").strip()
        if val:
            try:
                return max(0.08, min(1.5, float(val)))
            except ValueError:
                pass
    return 0.88


def record_noise_gate_rms() -> float:
    """
    Seuil RMS (0..1) pour ouvrir la porte ligne (parole audible).

    Filtre le souffle modem / ligne au repos.
    """
    raw = (os.environ.get("VG_PROSPECTOR_RECORD_NOISE_GATE") or "").strip()
    if raw:
        try:
            return max(0.004, min(0.12, float(raw)))
        except ValueError:
            pass
    return 0.034


def record_noise_gate_close_rms() -> float:
    """Seuil RMS pour refermer la porte (inferieur a l'ouverture = hysteresis)."""
    raw = (os.environ.get("VG_PROSPECTOR_RECORD_NOISE_GATE_CLOSE") or "").strip()
    if raw:
        try:
            return max(0.002, min(0.08, float(raw)))
        except ValueError:
            pass
    return 0.015


def record_arm_on_speech() -> bool:
    """
    Sortant : n'ouvre le fichier WAV qu'a la premiere parole detectee sur la ligne.

    Evite sonnerie et souffle VRX juste apres composition.
    """
    raw = (os.environ.get("VG_PROSPECTOR_RECORD_ARM_ON_SPEECH") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return True


def record_arm_speech_rms() -> float:
    """RMS minimal pour declencher l'enregistrement (sortant, mode parole)."""
    raw = (os.environ.get("VG_PROSPECTOR_RECORD_ARM_SPEECH_RMS") or "").strip()
    if raw:
        try:
            return max(0.01, min(0.2, float(raw)))
        except ValueError:
            pass
    return 0.042


def record_arm_speech_hits() -> int:
    """Nombre de blocs audio consecutifs au-dessus du seuil avant ouverture WAV."""
    raw = (os.environ.get("VG_PROSPECTOR_RECORD_ARM_SPEECH_HITS") or "").strip()
    if raw:
        try:
            return max(2, min(40, int(raw)))
        except ValueError:
            pass
    return 8


def record_arm_speech_crest() -> float:
    """
    Facteur de crete minimal (pic/RMS) pour considerer un bloc comme parole.

    La sonnerie / tonalite (~400 Hz) reste plate (crete ~1.4) ; la voix depasse ~2.
    """
    raw = (os.environ.get("VG_PROSPECTOR_RECORD_ARM_SPEECH_CREST") or "").strip()
    if raw:
        try:
            return max(1.2, min(6.0, float(raw)))
        except ValueError:
            pass
    return 2.0


def record_line_min_crest() -> float:
    """Crete minimale pour ecrire de l'audio ligne dans le WAV."""
    raw = (os.environ.get("VG_PROSPECTOR_RECORD_LINE_MIN_CREST") or "").strip()
    if raw:
        try:
            return max(1.2, min(6.0, float(raw)))
        except ValueError:
            pass
    return 1.85


def record_start_delay_s() -> float:
    """
    Delai apres ouverture VRX avant de demarrer le WAV (evite clics composition).

    @returns Secondes (defaut 0.35).
    """
    raw = (os.environ.get("VG_PROSPECTOR_RECORD_START_DELAY") or "").strip()
    if raw:
        try:
            return max(0.0, min(3.0, float(raw)))
        except ValueError:
            pass
    return 0.35


def record_calls_enabled() -> bool:
    """
    Enregistrement WAV des appels (ligne + micro) active par defaut.

    Desactiver avec ``VG_PROSPECTOR_RECORD_CALLS=0``, ui_prefs ``record_calls: false``.
    """
    try:
        from desktop.prospector.ui_prefs import load_prefs

        pref = load_prefs().get("record_calls")
        if pref is False:
            return False
        if pref is True:
            return True
    except Exception:
        pass
    raw = (os.environ.get("VG_PROSPECTOR_RECORD_CALLS") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def call_recordings_base_dir() -> Path:
    """
    Dossier racine des enregistrements (sous Documents/VocalGuard/prospector/recordings).

    Surcharge : ``VG_PROSPECTOR_RECORD_DIR`` (chemin absolu).
    """
    custom = (os.environ.get("VG_PROSPECTOR_RECORD_DIR") or "").strip()
    if custom:
        return Path(custom)
    docs = Path(os.environ.get("USERPROFILE", os.path.expanduser("~"))) / "Documents"
    return docs / "VocalGuard" / "prospector" / "recordings"
