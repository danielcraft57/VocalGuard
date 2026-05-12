#!/usr/bin/env python3
"""
Catalogue de modèles Vosk (français), téléchargement, profil disque, sélection interactive.

Les archives proviennent d’alphacephei.com ; le cache local par défaut est
``scripts/modem_lab/generated/vosk_models/``.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
import time
import uuid
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from loguru import logger

_MODEM_LAB = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE_PATH = _MODEM_LAB / "generated" / "vosk_lab_profile.json"
DEFAULT_CACHE_ROOT = _MODEM_LAB / "generated" / "vosk_models"

# Slug -> métadonnées (URL Alphacephei, répertoire après dézip)
FRENCH_MODELS: dict[str, dict[str, Any]] = {
    "small-fr": {
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip",
        "dir_name": "vosk-model-small-fr-0.22",
        "title": "Français compact",
        "hint": "Recommandé modem / latence / Raspberry Pi (~42 Mo, Apache 2.0)",
    },
    "fr-0.22": {
        "url": "https://alphacephei.com/vosk/models/vosk-model-fr-0.22.zip",
        "dir_name": "vosk-model-fr-0.22",
        "title": "Français grand",
        "hint": "Meilleure précision serveur (~1,4 Go, Apache 2.0)",
    },
    "pguyot-small": {
        "url": "https://alphacephei.com/vosk/models/vosk-model-small-fr-pguyot-0.3.zip",
        "dir_name": "vosk-model-small-fr-pguyot-0.3",
        "title": "Français compact (Guyot)",
        "hint": "Alternative légère (~39 Mo, licence CC-BY-NC-SA 4.0)",
    },
    "fr-linto": {
        "url": "https://alphacephei.com/vosk/models/vosk-model-fr-0.6-linto-2.2.0.zip",
        "dir_name": "vosk-model-fr-0.6-linto-2.2.0",
        "title": "Français LINTO (grand)",
        "hint": "Modèle projet LINTO (~1,5 Go, licence AGPL)",
    },
}

PROFILE_VERSION = 1


@dataclass
class VoskLabProfile:
    version: int = PROFILE_VERSION
    model_slug: str = ""
    model_path: str = ""
    cache_root: str = ""

    def to_json_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_json_dict(cls, d: dict[str, Any]) -> "VoskLabProfile":
        return cls(
            version=int(d.get("version", PROFILE_VERSION)),
            model_slug=str(d.get("model_slug") or ""),
            model_path=str(d.get("model_path") or ""),
            cache_root=str(d.get("cache_root") or ""),
        )


def default_cache_root() -> Path:
    return Path(DEFAULT_CACHE_ROOT)


def is_plausible_vosk_dir(path: Path) -> bool:
    """Heuristique : présence de fichiers typiques d’un modèle Vosk dépaqueté.

    Sur Windows, ``.is_file()`` / ``iterdir()`` peuvent lever ``PermissionError`` (fichier
    verrouillé, antivirus, autre processus) : on les ignore et on teste d’autres marqueurs.
    """
    try:
        if not path.is_dir():
            return False
    except (PermissionError, OSError):
        return False
    markers = (
        "am/final.mdl",
        "model.conf",
        "graph/HCLG.fst",
        "graph/Gr.fst",
        "conf/mfcc.conf",
    )
    for rel in markers:
        try:
            if (path / rel).is_file():
                return True
        except (PermissionError, OSError):
            continue
    # Variantes « lookahead » / certains ZIP : ``final.mdl`` + FST à la racine (ex. pguyot FR)
    try:
        if (path / "final.mdl").is_file() and (
            (path / "Gr.fst").is_file() or (path / "HCLr.fst").is_file()
        ):
            return True
    except (PermissionError, OSError):
        pass
    try:
        am = path / "am"
        if not am.is_dir():
            return False
        for _ in am.iterdir():
            return True
    except (PermissionError, OSError):
        pass
    return False


def _download(
    url: str,
    dest: Path,
    *,
    on_progress: Optional[Callable[[int, int], None]] = None,
    timeout_sec: int = 7200,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": "VocalGuard-modem-lab/1.0"})
    with urlopen(req, timeout=timeout_sec) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        block = 256 * 1024
        n = 0
        with open(dest, "wb") as f:
            while True:
                b = resp.read(block)
                if not b:
                    break
                f.write(b)
                n += len(b)
                if on_progress and total > 0:
                    on_progress(n, total)
    if dest.stat().st_size < 1024:
        raise OSError(f"Téléchargement trop petit: {dest}")


def _extract_zip(zip_path: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for m in zf.namelist():
            if m.startswith("/") or ".." in m.split("/"):
                raise OSError(f"Entrée zip rejetée (sécurité): {m}")
        zf.extractall(target_dir)


def _rmtree_robust(path: Path) -> None:
    """
    Supprime un répertoire (Windows : lecture seule, handles partiels).

    Plusieurs passes + ``chmod`` sur échec ; si le nom reste bloqué, renommage en
    ``*.stale_<timestamp>`` pour libérer le chemin attendu du modèle.
    """
    if not path.exists():
        return

    def _onerror(func: Any, p: str, _exc_info: Any) -> None:
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    for attempt in range(5):
        if not path.exists():
            return
        try:
            shutil.rmtree(path, onerror=_onerror)
        except OSError:
            pass
        if not path.exists():
            return
        time.sleep(0.2 * (attempt + 1))

    if not path.exists():
        return

    stale = path.parent / f"{path.name}.stale_{int(time.time())}"
    try:
        path.rename(stale)
        path = stale
    except OSError as e:
        logger.error("Suppression impossible « {} » : {}", path, e)
        raise OSError(
            f"Impossible de supprimer ou renommer le dossier (fichiers verrouillés ?) : {path}"
        ) from e

    for attempt in range(3):
        if not path.exists():
            return
        try:
            shutil.rmtree(path, onerror=_onerror)
        except OSError:
            pass
        if not path.exists():
            return
        time.sleep(0.3)

    if path.exists():
        logger.warning(
            "Cache Vosk : impossible de tout supprimer « {} » — supprimez ce dossier à la main si besoin.",
            path,
        )


def ensure_french_model(
    slug: str,
    *,
    cache_root: Optional[Path] = None,
    force_download: bool = False,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> Path:
    """
    Vérifie le répertoire du modèle ; si absent, télécharge et extrait l’archive.

    :returns: chemin absolu du dossier modèle (am/, graph/, …)
    :raises: KeyError si slug inconnu, OSError/URLError si échec réseau / zip
    """
    if slug not in FRENCH_MODELS:
        raise KeyError(f"Modèle inconnu: {slug!r} (voir --vosk-list-models)")
    meta = FRENCH_MODELS[slug]
    root = Path(cache_root) if cache_root is not None else default_cache_root()
    root.mkdir(parents=True, exist_ok=True)
    model_dir = (root / meta["dir_name"]).resolve()

    if not force_download and is_plausible_vosk_dir(model_dir):
        logger.info("Modèle Vosk déjà présent: {}", model_dir)
        return model_dir

    dl_dir = root / "_downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dl_dir / f"{meta['dir_name']}.zip"
    url = str(meta["url"])
    logger.info("Téléchargement Vosk ({}) depuis {}", slug, url)
    logger.info("Archive locale: {}", zip_path)

    def _prog(n: int, t: int) -> None:
        if on_progress:
            on_progress(n, t)
        elif t > 0:
            pct = 100 * n // t
            print(f"\r  Téléchargement… {pct:3d}% ({n // (1024 * 1024)} Mo / {t // (1024 * 1024)} Mo)", end="", flush=True)

    try:
        _download(url, zip_path, on_progress=_prog)
    except URLError as e:
        logger.exception("Échec téléchargement")
        raise
    finally:
        if on_progress is None:
            print(flush=True)

    # Extraire vers un nom unique sous ``root`` : si ``model_dir`` existe encore,
    # ``shutil.move(src, model_dir)`` déposerait ``src`` *à l’intérieur* (double dossier + PermissionError).
    staging: Path | None = None
    try:
        with tempfile.TemporaryDirectory(dir=str(root)) as tmp:
            tmp_p = Path(tmp)
            _extract_zip(zip_path, tmp_p)
            extracted: Path | None = None
            for c in sorted(tmp_p.iterdir()):
                if c.is_dir() and is_plausible_vosk_dir(c):
                    extracted = c
                    break
            if extracted is None:
                for c in tmp_p.rglob("*"):
                    if c.is_dir() and c.parent != tmp_p and is_plausible_vosk_dir(c):
                        extracted = c
                        break
            if extracted is None:
                raise OSError(f"Archive ZIP sans dossier modèle reconnu: {zip_path.name}")
            staging = (root / f"._vosk_extract_{uuid.uuid4().hex[:12]}").resolve()
            if staging.exists():
                _rmtree_robust(staging)
            shutil.move(str(extracted), str(staging))

        if not is_plausible_vosk_dir(staging):
            raise OSError(f"Archive ZIP corrompue ou incomplète: {zip_path.name}")

        _rmtree_robust(model_dir)
        if model_dir.exists():
            raise OSError(
                f"Impossible de remplacer le dossier (accès refusé) : {model_dir}. "
                "Fermez les autres processus qui utilisent ce modèle Vosk, puis réessayez."
            )
        staging.rename(model_dir)
        staging = None
    except Exception:
        if staging is not None and staging.exists():
            try:
                _rmtree_robust(staging)
            except Exception as e:
                logger.warning("Nettoyage staging Vosk « {} » : {}", staging, e)
        raise

    if not is_plausible_vosk_dir(model_dir):
        raise OSError(
            f"Extraction incomplète: dossier modèle non reconnu sous {model_dir}. "
            "Vérifiez l’espace disque ou retéléchargez."
        )
    logger.info("Modèle prêt: {}", model_dir)
    return model_dir


def ensure_all_french_models(
    *,
    cache_root: Optional[Path] = None,
    force_download: bool = False,
) -> dict[str, Path]:
    """
    Télécharge ou vérifie tous les modèles du catalogue ``FRENCH_MODELS`` (liste officielle FR sur alphacephei).

    :returns: slug → répertoire modèle absolu
    """
    out: dict[str, Path] = {}
    for slug in sorted(FRENCH_MODELS.keys()):
        out[slug] = ensure_french_model(
            slug, cache_root=cache_root, force_download=force_download
        )
    return out


def load_profile(path: Path | None = None) -> VoskLabProfile:
    p = path or DEFAULT_PROFILE_PATH
    if not p.is_file():
        return VoskLabProfile()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return VoskLabProfile()
        return VoskLabProfile.from_json_dict(data)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Profil Vosk illisible ({}), ignoré", e)
        return VoskLabProfile()


def save_profile(
    profile: VoskLabProfile,
    path: Path | None = None,
) -> None:
    p = path or DEFAULT_PROFILE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    profile.version = PROFILE_VERSION
    p.write_text(json.dumps(profile.to_json_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info("Profil Vosk enregistré: {}", p.resolve())


def print_models_catalog() -> None:
    """Affiche le tableau des modèles (stdout)."""
    print("\n  Modèles Vosk français disponibles (slug pour --vosk-model-slug):\n")
    print(f"  {'slug':<12}  {'titre':<22}  détail")
    print("  " + "-" * 72)
    for slug, m in FRENCH_MODELS.items():
        print(f"  {slug:<12}  {m['title']:<22}  {m['hint']}")
    print(f"\n  Cache par défaut : {default_cache_root()}")
    print(f"  Profil par défaut : {DEFAULT_PROFILE_PATH}")
    print(
        "  Tout télécharger : python scripts/modem_lab/cli.py answer-vosk-live-probe "
        "-- --vosk-download-all-fr\n"
    )


def interactive_pick_slug() -> str:
    """Menu numéroté sur stderr pour éviter de polluer stdout pipe."""
    lines = list(FRENCH_MODELS.items())
    print("\n── Choix du modèle Vosk (français) ──", file=sys.stderr)
    for i, (slug, m) in enumerate(lines, start=1):
        print(f"  [{i}] {slug} — {m['title']}", file=sys.stderr)
        print(f"      {m['hint']}", file=sys.stderr)
    while True:
        print("Votre choix [1-{}] (Entrée = 1) : ".format(len(lines)), end="", file=sys.stderr, flush=True)
        raw = sys.stdin.readline() if sys.stdin else ""
        if not raw:
            return lines[0][0]
        raw = raw.strip()
        if not raw:
            return lines[0][0]
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(lines):
                return lines[idx - 1][0]
        for slug in FRENCH_MODELS:
            if raw.lower() == slug.lower():
                return slug
        print("  Saisie invalide.", file=sys.stderr)


def resolve_vosk_model_dir(
    *,
    explicit_path: Path | None,
    model_slug: str | None,
    profile_path: Path,
    cache_root: Path | None,
    env_path: str | None,
    interactive: bool,
    save_profile_flag: bool,
) -> tuple[Optional[Path], Optional[str]]:
    """
    Résout le répertoire du modèle.

    Ordre :
    1. ``explicit_path`` si dossier valide
    2. ``model_slug`` → ensure téléchargement
    3. variable d’environnement (``env_path`` ou ``VOSK_MODEL_PATH``)
    4. profil : ``model_path`` si dossier valide
    5. profil : ``model_slug`` + ensure
    6. ``interactive`` (TTY) → choix + ensure

    Si ``save_profile_flag`` : enregistre ``model_slug`` / ``model_path`` dans le profil.

    :returns: (path, slug_utilisé pour ce run)
    """
    cr = cache_root
    path: Optional[Path] = None
    slug_out: Optional[str] = None

    if explicit_path is not None:
        p = Path(explicit_path).resolve()
        if is_plausible_vosk_dir(p):
            path = p
            prof = load_profile(profile_path)
            slug_out = (model_slug.strip() if model_slug else None) or (
                prof.model_slug if prof.model_slug else None
            )
        else:
            logger.warning("Chemin --vosk-model invalide ou incomplet: {}", p)

    if path is None and model_slug and model_slug.strip() in FRENCH_MODELS:
        s = model_slug.strip()
        path = ensure_french_model(s, cache_root=cr)
        slug_out = s

    if path is None:
        ev = (env_path or "").strip() or os.environ.get("VOSK_MODEL_PATH", "").strip()
        if ev:
            p = Path(ev).resolve()
            if is_plausible_vosk_dir(p):
                path = p
                slug_out = None

    prof = load_profile(profile_path)
    if path is None and prof.model_path:
        p = Path(prof.model_path).resolve()
        if is_plausible_vosk_dir(p):
            path = p
            slug_out = prof.model_slug or None
            logger.info("Profil Vosk : modèle {}", path)

    if path is None and prof.model_slug and prof.model_slug in FRENCH_MODELS:
        cr_use = Path(prof.cache_root).resolve() if prof.cache_root else cr
        path = ensure_french_model(prof.model_slug, cache_root=cr_use)
        slug_out = prof.model_slug

    if path is None and interactive and sys.stdin.isatty():
        s = interactive_pick_slug()
        path = ensure_french_model(s, cache_root=cr)
        slug_out = s
        logger.info("Modèle choisi interactif: {} -> {}", s, path)

    if save_profile_flag and path is not None:
        prof_w = load_profile(profile_path)
        if slug_out:
            prof_w.model_slug = slug_out
        prof_w.model_path = str(path.resolve())
        if cr is not None:
            prof_w.cache_root = str(cr.resolve())
        elif not prof_w.cache_root:
            prof_w.cache_root = str(default_cache_root().resolve())
        save_profile(prof_w, profile_path)

    return path, slug_out


def run_configure_only_flow(
    *,
    profile_path: Path,
    cache_root: Path | None,
    model_slug: str | None,
    interactive: bool,
    list_only: bool,
    download_all_fr: bool = False,
) -> int:
    """Utilitaire --vosk-configure-only / --vosk-list-models / --vosk-download-all-fr (sans modem)."""
    if list_only:
        print_models_catalog()
        return 0
    if download_all_fr:
        paths = ensure_all_french_models(cache_root=cache_root)
        cr = cache_root.resolve() if cache_root else default_cache_root().resolve()
        print("\nModèles Vosk français (catalogue projet = liste alphacephei FR + FR Other) :\n")
        for slug, pth in sorted(paths.items()):
            print(f"  {slug:<14}  {pth}")
        print(f"\nRacine cache : {cr}\n")
        print(
            "Le profil JSON n’est pas modifié. Pour enregistrer un modèle par défaut : "
            "--vosk-configure-only --vosk-model-slug …\n",
            flush=True,
        )
        return 0
    slug = model_slug
    if not slug and interactive and sys.stdin.isatty():
        slug = interactive_pick_slug()
    elif not slug:
        prof = load_profile(profile_path)
        if prof.model_slug in FRENCH_MODELS:
            slug = prof.model_slug
        else:
            print("Indiquez --vosk-model-slug … ou --vosk-interactive sur un terminal.", file=sys.stderr)
            print_models_catalog()
            return 2
    path = ensure_french_model(slug, cache_root=cache_root)
    prof = load_profile(profile_path)
    prof.model_slug = slug
    prof.model_path = str(path)
    prof.cache_root = str(cache_root.resolve()) if cache_root else str(default_cache_root().resolve())
    save_profile(prof, profile_path)
    print(f"\nModèle prêt : {path}", flush=True)
    print(f"Profil écrit : {profile_path.resolve()}", flush=True)
    return 0
