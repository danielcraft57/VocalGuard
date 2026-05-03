# Guide des capacités — modem analogique 56K US Robotics (lab VocalGuard)

Ce document décrit **ce qu’il est possible de faire** avec un modem « controller-based » du type documenté dans ce dossier (référence matérielle principale du projet : **5637 OEM** USB, PDF local ; référence commandes Hayes génériques : synthèses **5631**). Il agrège les fiches `5637-*.md` et les synthèses Hayes (guide USR 5631) sans remplacer le PDF ni les pages USR.

---

## 1. Vue d’ensemble : un modem sur ligne analogique

### 1.1 Rôle du boîtier

Le modem relie :

- un **ordinateur** (ici souvent **USB** → port série logique type `/dev/ttyACM*`) ;
- une **ligne téléphonique analogique** (RJ-11), pas une ligne téléphonique **numérique** directe (risque matériel).

Sur cette base, il peut assurer plusieurs **métiers** selon le mode logiciel (`+FCLASS` et pile applicative) :

| Métier | Standards / usage typique |
|--------|---------------------------|
| **Données / « Internet »** | Liaison vers un **fournisseur ou équipement distant** compatible (handshake V série, V.42, compression, éventuellement **PPP** côté OS) |
| **Télécopie** | **T.30** entre modems fax ; classes AT **1 / 1.0 / 2** |
| **Voix** | **V.253** : messagerie, annonces, enregistrement, tonalités, parfois mains-libres |
| **Téléphonie de contrôle** | Numérotation, décroché, raccroché, détection tonalités, **caller ID** si la ligne le permet |

Une même ligne permet **en principe** ces usages à des moments différents ; en pratique le projet **VocalGuard / modem_lab** se concentre sur **voix + contrôle d’appel** sur matériel réel ou simulé. La **correspondance documentation ↔ fichiers Python** (scénarios, `ModemHandler`, détection de décroché) est en **§12** ; le détail *décroché distant / volume audio* en **§13**.

### 1.2 Limites réseau « Internet » (rappel honnête)

- Le débit **descendant** peut monter vers **56 kbit/s** dans les meilleurs cas (**V.90** / **V.92** selon ligne et pair).
- Le débit **montant** reste **analogique** (sauf **PCM upstream V.92** si opérateur et pair le supportent — voir [v92-p-commands.md](./v92-p-commands.md)).
- La qualité dépend de la **boucle locale**, du **codec** côté central, et du fait que la voie soit une **connexion commutée** classique (aujourd’hui rare comme accès principal).

Ce modem **n’est pas un routeur DSL/Fibre** : l’« Internet » passe par **composition d’un numéro** et **négociation avec un autre modem** (ou équipement compatible), puis une couche réseau (souvent **PPP**) sur l’ordinateur.

---

## 2. Choix du mode : `+FCLASS` (classe de service)

La commande **`AT+FCLASS=<mode>`** sélectionne le « métier » du modem côté AT :

| Mode | Service | Orientation doc |
|------|---------|------------------|
| **0** | **Données** | [commandes-generiques-et-profil.md](./commandes-generiques-et-profil.md), [modulation.md](./modulation.md), [controle-erreur.md](./controle-erreur.md) |
| **1** / **1.0** | Fax **classe 1** / **1.0** | Manuels fax + pilotes applicatifs |
| **2** | Fax **classe 2** | Idem |
| **8** | **Voix** (V.253) | [5637-commandes-voix.md](./5637-commandes-voix.md) |

Après usage voix ou fax, le retour au mode données usuel se fait typiquement par **`AT+FCLASS=0`** (ou reset profil).

---

## 3. Données et accès réseau (« Internet dial-up »)

### 3.1 Chaîne protocolaire

1. **Physique / liaison** : tonalités V.25, **V.8** si disponible, puis porteuse (**V.34**, **V.90**, **V.92**, etc.) — réglages **`+MS`**, voir [modulation.md](./modulation.md).
2. **Correction d’erreur** : **V.42 LAPM** ou **MNP** — **`+ES`**, **`&M`**, [controle-erreur.md](./controle-erreur.md).
3. **Compression sur la liaison modem-modem** : **V.42bis** / **MNP5** — **`&K`**, `+DS` (chapitre compression du guide complet).
4. **Couche réseau sur le PC** : le plus souvent **PPP** (`pppd`, NetworkManager, anciens accès FAI).

### 3.2 Commandes AT utiles (résumé)

- **Composition** : **`ATD`** et modificateurs (`T`/`P`, pauses, flash…) — [controle-appel.md](./controle-appel.md). En lab : composition simple `scripts/modem_lab/labscenarios/dialer.py`, appels sortants riches `labscenarios/outbound_announce.py` et `outgoing_call.py` (voir §12).
- **Réponse entrante** : **`ATA`**, sonneries **`S0`**, timeouts **`S7`**… — même fichier et [registres-s-index.md](./registres-s-index.md).
- **Qualité de lien / diagnostic** : **`ATI6`**, **`#UD`** — [diagnostic-et-ud.md](./diagnostic-et-ud.md).
- **V.92** : mise en attente, PCM amont, phases courtes — [v92-p-commands.md](./v92-p-commands.md).

### 3.3 Interface PC ↔ modem

Débit série (**+IPR**), flux matériel/logiciel (**&H**, **&R**, **+IFC**), messages **CONNECT** (**W**, **X**) — [interface-dte.md](./interface-dte.md).

---

## 4. Fax

### 4.1 Principe

En **`+FCLASS=1`**, **`1.0`** ou **`2`**, le modem se comporte comme **modem fax** : la suite **T.30** (phases A–E) est en général pilotée par une **application fax** (spooler, serveur, ou logiciel dédié) qui envoie les commandes fax étendues (`+F…`) appropriées à la classe.

### 4.2 Côté « téléphone »

- **`ATD`** en mode fax enchaîne vers les états décrits dans le guide (ex. attente signal fax).
- Paramètres **pays** (**+GCI**), niveaux **fax** (**S92** sur 5631), sont dans les références génériques / registres.

Pour une mise en œuvre complète fax sous Linux ou Windows, se référer au **manuel PDF du modem** (sections Fax) et aux logiciels (ex. HylaFAX, drivers constructeur) : ce dépôt ne les détaille pas ligne à ligne.

---

## 5. Voix (messagerie, annonces, tonalités)

### 5.1 Entrée en mode voix

- **`AT+FCLASS=8`** — voir [5637-commandes-voix.md](./5637-commandes-voix.md).

### 5.2 Routing audio analogique : `+VLS`

Indispensable pour savoir si le modem est **en ligne**, **décroché**, **micro / HP / combiné** — table **`AT+VLS=`** dans la même fiche. Le lab utilise souvent **`AT+VLS=1`** pour parler sur la ligne après décroché.

### 5.3 Format des échantillons : `+VSM`

Exemples : **PCM 8 bits** ou **16 bits**, **8 kHz**, ADPCM, μ-law/A-law — compatibilité à valider avec **`AT+VSM=?`**.

### 5.4 Flux série bidirectionnel

- **`AT+VTX`** : jouer un message / flux vers la ligne.
- **`AT+VRX`** : enregistrer depuis la ligne.
- **`AT+VTR`** : full duplex selon contexte.

Échappements et **codes DLE** : [5637-dle-et-flux-serie.md](./5637-dle-et-flux-serie.md). Pont micro / HP en lab : `scripts/modem_lab/labscenarios/incoming_call.py` + `labcore/live_audio.py` (§12).

### 5.5 Réglages vocaux courants

Gain / volume (**+VGM**, **+VGR**, **+VGT**…), silence (**+VSD**), tonalités et DTMF (**+VTS**, **+VTD**), timers (**+VRA**, **+VRN**, **+VIT**), mains-libres (**+VSP**, **+VLS** combinaisons) — tout est centralisé dans [5637-commandes-voix.md](./5637-commandes-voix.md).

---

## 6. Répondeur téléphonique (TAD)

Scénario documenté : message d’accueil, bip, enregistrement, fin par silence — [5637-scenarios-repondeur.md](./5637-scenarios-repondeur.md).

En résumé fonctionnel :

1. Détection **RING** (et éventuellement **caller ID** avant décroché — **`+VCID`**).
2. Passage **`+FCLASS=8`**, configuration **+VSM** / **+VSD** (souvent silence désactivé pendant le prompt).
3. **`+VLS`** pour décrocher sur la ligne.
4. **`+VTX`** pour le message, fin **`DLE`+`ETX`**.
5. **`+VTS`** pour le bip.
6. **`+VRX`** pour le message entrant, gestion fin via **+VSD** et codes **DLE** (**`<DLE>s`**, etc.).
7. **`ATH`**, puis **`AT+FCLASS=0`** si besoin.

**Implémentation dans le dépôt :**

| Rôle | Chemin (depuis la racine du dépôt) |
|------|-------------------------------------|
| Séquence répondeur (accueil, bip, enregistrement) | `scripts/modem_lab/labscenarios/answering_machine.py` |
| Décroché / lecture WAV utilitaires | `labcore/answer.py`, `labcore/voice_line.py`, `labcore/hangup.py`, `labcore/call_control.py`, `labcore/line_audio_player.py` |
| Modem série voix (ATA, +VTX/+VRX, attente décroché sortant) | `backend/core/modem_handler.py` |

---

## 7. « Téléphone » au sens classique (sans forcément voix avancée)

Même sans messagerie logicielle, le modem peut :

| Fonction | Moyens AT |
|----------|-----------|
| Composer un numéro | **`ATD`**, **`ATDL`** (dernier numéro), répertoire **`&Z`** |
| Répondre | **`ATA`**, auto-réponse **`S0>0`** |
| Raccrocher | **`ATH`**, ou chute **DTR** selon **`&D`** |
| Entendre la ligne | Haut-parleur **`L`**, **`M`** (volume / quand) |
| Flash / seconde ligne | **`!`** dans la chaîne de dial (**S29**), ou séquences V.92 MOH — selon contexte |
| Identifier l’appelant | **`+VCID`**, lecture **`+VRID`** — si le réseau envoie le CID |
| Limiter les tentatives | Listes opérateur / **`*B`** (blacklist) selon pays |

---

## 8. Diagnostics et maintenance logique

| Objectif | Commande / action |
|----------|-------------------|
| Identité matérielle / firmware | **`ATI0`–`ATI7`**, **`AT+GCI?`** |
| Configuration active | **`ATI4`**, **`AT&V`** (profils **&W** / **Z**) |
| Dernier appel données | **`ATI6`**, **`#UD`** — [diagnostic-et-ud.md](./diagnostic-et-ud.md) |
| Test boucle (si conditions remplies) | **`&T`** — [commandes-generiques-et-profil.md](./commandes-generiques-et-profil.md) |

---

## 9. Tableau : objectif → mode → lecture

| Objectif | `+FCLASS` | Documents à ouvrir en priorité |
|----------|-----------|--------------------------------|
| Accès distant type FAI / liaison modem-modem | 0 | [controle-appel.md](./controle-appel.md), [modulation.md](./modulation.md), [controle-erreur.md](./controle-erreur.md), [interface-dte.md](./interface-dte.md) |
| Envoyer / recevoir un fax | 1, 1.0 ou 2 | PDF 5637 + logiciel fax ; [commandes-generiques-et-profil.md](./commandes-generiques-et-profil.md) |
| Annonce vocale, messagerie, répondeur | 8 | [5637-commandes-voix.md](./5637-commandes-voix.md), [5637-scenarios-repondeur.md](./5637-scenarios-repondeur.md), [5637-dle-et-flux-serie.md](./5637-dle-et-flux-serie.md) |
| Optimiser V.92 (MOH, PCM amont, reprise rapide) | 0 (+ config V.92) | [v92-p-commands.md](./v92-p-commands.md) |
| Comprendre tous les registres | — | [registres-s-index.md](./registres-s-index.md), [5637-registres-s.md](./5637-registres-s.md) |
| Rappels syntaxe AT | — | [5637-conventions-at.md](./5637-conventions-at.md), [usr-guide-index.md](./usr-guide-index.md) |

---

## 10. Matériel et sécurité

- Ligne **analogique** ; pas de branchement direct sur **RNIS** / certaines PABX **numériques** sans adaptateur adapté (voir **5637-apercu** et manuel constructeur).
- **Surveillance légale** : enregistrer des conversations peut être **réglementé** ; respecter le droit local.
- **Isolation** : tonneries secteur, orages — précautions classiques modem téléphonique.

---

## 11. Index du dossier `docs/`

| Fichier | Contenu |
|---------|---------|
| [5637-apercu.md](./5637-apercu.md) | Produit 5637, USB, LED, Linux |
| [5637-conventions-at.md](./5637-conventions-at.md) | V.250, syntaxe `+` |
| [5637-commandes-voix.md](./5637-commandes-voix.md) | Référence **`+V*`** |
| [5637-dle-et-flux-serie.md](./5637-dle-et-flux-serie.md) | DLE, **+VTX** / **+VRX** |
| [5637-registres-s.md](./5637-registres-s.md) | Registres **S** utiles 5637 |
| [5637-scenarios-repondeur.md](./5637-scenarios-repondeur.md) | Séquences TAD |
| [usr-guide-index.md](./usr-guide-index.md) | Index des fiches 5631 + URLs |
| [commandes-generiques-et-profil.md](./commandes-generiques-et-profil.md) | Profils, **+FCLASS**, CID, **I**, **&W**… |
| [interface-dte.md](./interface-dte.md) | Echo, flux, **CONNECT** |
| [controle-appel.md](./controle-appel.md) | **D**, **H**, **A**, pulse/tonal |
| [modulation.md](./modulation.md) | **+MS**, **+MR** |
| [controle-erreur.md](./controle-erreur.md) | **+ES**, **+ER** |
| [diagnostic-et-ud.md](./diagnostic-et-ud.md) | **#UD** |
| [v92-p-commands.md](./v92-p-commands.md) | **+PMH**, **+PCW**, … |
| [registres-s-index.md](./registres-s-index.md) | Liste **S** 5631 |
| [guide-capacites-modem-56k-complet.md](./guide-capacites-modem-56k-complet.md) | Ce guide (capacités + code §12–13) |

---

## 12. Cartographie documentation ↔ code (`modem_lab` et backend)

Les chemins sont relatifs à la **racine du dépôt** VocalGuard.

### 12.1 Cœur modem et événements série (voix / Hayes)

| Fichier | Rôle |
|---------|------|
| `backend/core/modem_handler.py` | Initialisation, `+FCLASS=8`, `+VTX` / `+VRX`, lecture WAV vers la ligne, attente **décroché sortant** (`_wait_voice_outbound_answer_sync`), DTMF, raccrochage. |
| `backend/core/telephony_events/serial_analysis.py` | `remote_pickup_likely`, `analyze_serial_voice_buffer`, comptage **DLE+R**, résumé `outbound_wait_status_summary`. |
| `backend/core/telephony_events/dle_voice.py` | Codes **DLE** documentés 5637 (dont indice « answer tone » **DLE+a**). |
| `backend/core/telephony_events/__init__.py` | Point d’entrée du paquet ; références V.253 / manuel. |

### 12.2 Scénarios CLI sous `scripts/modem_lab/`

| Fichier | Rôle |
|---------|------|
| `labscenarios/answering_machine.py` | Répondeur : auto-réponse, message d’accueil WAV, bip, enregistrement message. |
| `labscenarios/outbound_announce.py` | Appel sortant : annonce WAV, options **`--wait-answer-tone`**, **`--voice-blind-dial`**, délais sonnerie — voir docstring (composition voix vs données). |
| `labscenarios/outbound_listen_vad.py` | Appel **sans WAV** : après dial / attentes, **VRX + VAD** uniquement (logs « ça parle »). |
| `labscenarios/outgoing_call.py` | Appel sortant interactif (DTMF après composition). |
| `labscenarios/dialer.py` | Numérotation simple + maintien ligne puis raccrochage. |
| `labscenarios/incoming_call.py` | Appel entrant + pont audio **`LiveAudioBridge`** (`labcore/live_audio.py`). |
| `labscenarios/smoke_tests.py` | Tests de fumée orchestrés. |
| `modem_lab_ui.py` | Interface du lab (si utilisée). |

### 12.3 Bibliothèque partagée `labcore/`

| Fichier | Rôle |
|---------|------|
| `labcore/bootstrap.py` | Arguments CLI modem (port, débit), construction **`ModemHandler`**. |
| `labcore/answer.py` | Décrochage rapide sur **RING**. |
| `labcore/voice_line.py` | Lecture / enregistrement WAV sur la ligne (repli / helpers). |
| `labcore/call_control.py` | **`CallController`** : décroché (rapide / complet), composition, DTMF, préparation voix, raccrochage turbo ou ATH simple, commande AT brute. |
| `labcore/line_audio_player.py` | **`LineAudioPlayer`** : WAV ou buffer PCM u8 vers la ligne ; **`preview_wav_on_host`** : lecture locale (sounddevice / pyaudio). |
| `labcore/hangup.py` | Raccrochage « turbo » utilisé par les scénarios. |
| `labcore/live_audio.py` | Pont micro ↔ modem pour écoute conversationnelle. |
| `labcore/voice_activity.py` | **`SpeechActivityDetector`** : événements **`speech_start` / `speech_end`** sur PCM u8 (MAD ou RMS), option **adaptatif** (plancher de bruit). |
| `labcore/pcm_metrics.py` | MAD / RMS / découpage trames pour analyse hors modem. |
| `labcore/pcm_tone.py` | Signaux de test (sinusoïde, silence) 8 kHz u8. |
| `labcore/pcm_file.py` | Lecture WAV → PCM u8 pour tests **offline** du VAD. |
| `labcore/ring_timing.py` | **`ringback_wait_sec`** — budget temps sonneries (aligné sur `outbound_announce`). |
| `labcore/vrx_vad_pump.py` | **`pump_vrx_speech_events`** : lit ``ModemHandler.read_vrx_chunk``, déclenche callbacks sur ``VaEvent`` (pré-requis : flux VRX ouvert). |
| `labcore/vrx_wav_recorder_thread.py` | **`VrxWavRecorderThread`** / **`submit_vrx_wav_record`** : enregistrement WAV ligne via ``record_wav_line_fallback``, planifié sur la boucle asyncio du modem depuis un autre thread. |
| `outbound_demo_fr.py` (racine `scripts/modem_lab/`) | Raccourci d’appel : **0780833873**, ``--voice-blind-dial``, ``--wait-answer-tone``, **5×4 s** sonneries — exige ``--message-wav`` et ``--port``. |

### 12.4 Application principale (hors dossier `modem_lab`)

| Fichier | Rôle |
|---------|------|
| `backend/api/routes/calls.py` | Sessions **appels sortants** (composition, état connecté, streaming STT, etc.). |
| `backend/core/call_manager.py` | Boucle appels entrants VocalGuard (répondeur produit). |

---

## 13. Décroché distant : savoir si la personne a répondu ? Volume sur la ligne ?

### 13.1 Ce que le modem expose (sans analyser le PCM)

En mode **voix** (`+FCLASS=8`), le **port série** reçoit en général :

- du **texte** : résultats AT (**`CONNECT`**, **`VCON`**, codes numériques si **`ATV0`**) ;
- des **échappements binaires** : préfixe **DLE** (0x10) + **octet de signal** (sonnerie **R**, tonalité réponse **a**, occupé **b**, silence **s**, etc. — voir manuel 5637 *Events Reported to the DTE* et [5637-dle-et-flux-serie.md](./5637-dle-et-flux-serie.md)).

Le projet considère qu’un **décroché distant est plausible** lorsque le tampon série contient notamment (**`backend/core/telephony_events/serial_analysis.py`**) :

- **DLE+a** — indice « answer tone » / ligne établie côté modem ;
- ou les chaînes **`CONNECT`** / **`VCON`** ;
- ou un **code résultat numérique 1** (style CONNECT en verbeux court).

C’est une **heuristique** : selon l’opérateur, le pays et le **mobile vs fixe**, le modem peut rester **muet** sur ces motifs pendant la sonnerie, ou ne pas distinguer messagerie vocale et humain. D’où les options du scénario **`outbound_announce`** (`--voice-blind-dial`, `--wait-answer-tone`, budgets temps / sonneries).

En **`+FCLASS=0`** seul vers un téléphone **voix**, il n’y a souvent **pas** de porteuse données : pas de **`CONNECT`** utile — ce cas est explicitement commenté dans la docstring de `outbound_announce.py`.

### 13.2 « Entendre » la ligne et envoyer un événement quand le volume augmente

- Le modem **ne** fournit **pas** un flux « niveau sonore » sur la liaison AT : l’audio utile est le flux **PCM** après **`AT+VRX`** puis réponse **`CONNECT`** (ou équivalent), octets **8 kHz** 8-bit dans le projet.
- **`AT+VSD`** règle la **détection de silence** côté modem (seuil + durée) et peut produire des **événements DLE** (ex. fin de silence / timer) — ce n’est pas équivalent à un VAD « dès que ça parle » configurable comme un logiciel audio ; voir [5637-commandes-voix.md](./5637-commandes-voix.md).
- Pour déclencher un **événement applicatif** du type « énergie audio > seuil » (approximation « quelqu’un parle ») :

  1. **Consommer le flux VRX** (ou un enregistrement ALSA en parallèle) ;
  2. calculer une **énergie courte** (RMS sur fenêtre glissante) sur les échantillons ;
  3. comparer à un **seuil** et émettre votre signal (callback, queue asyncio, etc.).

Ce pipeline **n’est pas implémenté** dans `telephony_events` aujourd’hui ; `incoming_call.py` illustre surtout le **pont live** micro/haut-parleur. Le module **`labcore/voice_activity.py`** fournit cette analyse PCM partagée ; branchement typique : boucle lecture **`read_vrx_chunk`** / **`serial.read`** → **`SpeechActivityDetector.feed`** → callback métier sur **`VaEvent`**.

### 13.3 Synthèse

| Besoin | Approche réaliste dans ce projet |
|--------|-----------------------------------|
| « La ligne est passée en conversation » | Priorité aux **événements série** : **DLE+a**, **CONNECT**/**VCON**, fonctions **`remote_pickup_likely`**. |
| « Le niveau audio monte » | **Traitement PCM** (VRX ou fichier), pas les seuls octets de commande AT. |
| « Fin de parole / silence » | **`+VSD`** + codes **DLE** associés, ou analyse PCM côté application. |

---

*Document de synthèse : à faire évoluer avec les choix concrets du firmware (réponses `ATI`, `+GCAP`, `=?`) sur votre modem.*
