# G1 Agent Interim

Agent vocal d'accueil pour **I-Interim** sur robot **Unitree G1 EDU** (Jetson Orin NX).

Le LLM tourne dans le cloud (OpenAI Realtime API). Tout le reste — audio, vision, gestes, tools — s'exécute en local sur le Jetson.

---

## Lancement

```bash
cd /home/unitree/unitree_sdk2_python && python3.8 /home/unitree/g1_agent_interim/main.py
```

> Toujours lancer depuis `/home/unitree/unitree_sdk2_python` — requis par le SDK Unitree.

Avec supervision ESP32 (bouche/émotions) :

```bash
cd /home/unitree/unitree_sdk2_python && python3.8 /home/unitree/g1_agent_interim/launch.py
```

---

## Architecture

```text
┌─ Cloud OpenAI ──────────────┐         ┌─ Jetson Orin NX ──────────────────────┐
│ gpt-realtime-mini           │◀──WSS──▶│ main.py (asyncio)                     │
│  • écoute l'audio micro     │ audio + │  • capture micro / joue le HP         │
│  • décide les tool calls    │ events  │  • exécute les tools                  │
│  • génère l'audio réponse   │         │  • supervise vision + librespot       │
└─────────────────────────────┘         └───────────────────────────────────────┘
```

---

## Arborescence

```text
g1_agent_interim/
├── main.py                  # Point d'entrée : init hardware + supervision subprocesses
├── launch.py                # Superviseur ESP32 (bouche/émotions) — couche optionnelle
├── config.py                # Clés API, voix, system prompts (IINTERIM / CDG)
├── agent/
│   ├── session.py           # Connexion WebSocket OpenAI Realtime
│   └── events.py            # Boucles async : audio, events, face/rps/fall/fire loops
├── robot/
│   ├── audio.py             # Micro USB + lecture HP (resampling numpy)
│   ├── arm_sdk.py           # Contrôle bras DDS bas niveau
│   ├── gestures.py          # execute_gesture() — ACTION_MAP geste→code
│   └── spotify_player.py    # librespot → resample → HP
├── tools/                   # Tools exposés au LLM via registry
│   ├── registry.py          # register() / get_schemas() / call()
│   ├── calendar_tool.py     # 6 tools Google Calendar (agenda, RDV, créneaux)
│   ├── vision_tool.py       # ce_que_je_vois + identifier_personne
│   ├── airlabs_tools.py     # 7 tools vols temps réel (Airlabs API)
│   ├── googlemaps_tools.py  # 7 tools lieux/itinéraires (Google Maps)
│   ├── transport_tools.py   # 5 tools transport IDF (geroTransport)
│   ├── spotify_tool.py      # 4 tools Spotify (jouer/contrôle/volume)
│   ├── gesture_tool.py      # executer_geste + relacher_bras
│   ├── screenshot_tool.py   # prendre_screenshot + envoi email
│   ├── qr_tool.py           # scanner_billet (QR code boarding pass)
│   ├── datetime_tool.py     # date_heure_actuelle
│   └── web_search.py        # recherche_web (Serper API)
├── scripts/                 # Setup OAuth one-shot (pas des tools agent)
│   ├── calendar_setup.py    # Génère le token Google Calendar (lecture + écriture)
│   ├── gmail_setup.py       # Génère le token Gmail OAuth
│   └── spotify_setup.py     # Auth Spotify (librespot OAuth)
└── vision/
    ├── vision_server.py     # YOLO dual-cam (UGREEN + RealSense) → /tmp/vision_state.json
    ├── face_id/             # InsightFace GPU → /tmp/face_id_state.json
    ├── fall_detection/      # YOLOv11 détection de chute → /tmp/fall_state.json
    ├── fire_detection/      # YOLOv26 détection feu/fumée → /tmp/fire_state.json
    └── rps/                 # Mini-jeu Pierre Feuille Ciseaux
```

---

## Double mode

Deux configurations disponibles — basculer dans `config.py` :

| Mode          | Variable                 | Usage                                              |
|---------------|--------------------------|----------------------------------------------------|
| **I-Interim** | `SYSTEM_PROMPT_IINTERIM` | Accueil agence intérim (RDV, Gmail, transport IDF) |
| **CDG**       | `SYSTEM_PROMPT_CDG`      | Accueil Terminal 2F CDG (vols, Google Maps)        |

---

## Variables d'environnement

Chargées depuis `~/.env` :

```text
OPENAI_API_KEY
SERPER_API_KEY
GOOGLE_MAPS_API_KEY
AIRLABS_API_KEY
SPOTIFY_CLIENT_ID
SPOTIFY_CLIENT_SECRET
```

---

## Prérequis

- **Python 3.8** — obligatoire (SDK Unitree + TensorRT)
- **SDK Unitree** : `/home/unitree/unitree_sdk2_python`
- Dépendances : `pip install -r requirements.txt`

---

## Documentation complète

Voir **[CLAUDE.md](CLAUDE.md)** — architecture détaillée, diagnostic, hardware, réseau, vision.
