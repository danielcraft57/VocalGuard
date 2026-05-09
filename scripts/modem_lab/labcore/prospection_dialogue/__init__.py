"""
Prospection téléphonique sortante : logique de **dialogue** réutilisable par ``prospection_outbound``.

Ce paquet regroupe :

- **config** : paramètres stables d’une session (nombre max de tours, tags terminaux, etc.).
- **snapshot** : état mutable **sérialisable** d’un appel (memento léger : tours joués, arrêt demandé).
- **chain** : **chaîne de responsabilité** sur plusieurs fichiers JSON d’intents (ordre = priorité).
- **opening** : choix du **premier WAV** joué (ouverture), ex. tirage aléatoire parmi les variantes d’un tag.
- **deadline** : budget temps wall-clock monotonic (tronquer les écoutes STT).
- **specification** : règles composables « peut-on lancer le tour N ? » (Specification + Composite).
- **events** : bus **Observer** pour logs / métriques sans coupler le scénario.
- **ports** : ``Protocol`` pour matcher d’intents (inversion de dépendance).
- **policy** : **Strategy** — regroupe config, timings, spec de poursuite, bus d’événements.

Le scénario ``labscenarios/prospection_outbound.py`` orchestre modem + Vosk ; ici on ne dépend pas du matériel.
"""

from .audio_cache import ProspectionAudioCache, build_prospection_audio_cache
from .chain import IntentChain, IntentMatchResult
from .config import ProspectionDialogueConfig
from .deadline import CallDeadline
from .events import DialogueEventBus, DialogueEventKind, DialogueEvent, loguru_dialogue_sink
from .opening import infer_opening_tag_from_intent_json_paths, pick_opening_wav_from_pack
from .policy import ProspectionDialoguePolicy, build_dialogue_policy
from .ports import IntentMatcherProtocol
from .snapshot import ConversationSnapshot
from .specification import (
    AllOfSpecifications,
    DialogueContext,
    DialogueSpecification,
    default_continue_dialogue_spec,
)

__all__ = [
    "AllOfSpecifications",
    "ProspectionAudioCache",
    "build_prospection_audio_cache",
    "build_dialogue_policy",
    "CallDeadline",
    "ConversationSnapshot",
    "DialogueContext",
    "DialogueEvent",
    "DialogueEventBus",
    "DialogueEventKind",
    "DialogueSpecification",
    "default_continue_dialogue_spec",
    "infer_opening_tag_from_intent_json_paths",
    "IntentChain",
    "IntentMatcherProtocol",
    "IntentMatchResult",
    "loguru_dialogue_sink",
    "pick_opening_wav_from_pack",
    "ProspectionDialogueConfig",
    "ProspectionDialoguePolicy",
]
