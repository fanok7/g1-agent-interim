# G1 Agent Interim — Documentation

Agent vocal d'accueil pour I-Interim sur robot Unitree G1 EDU (Jetson Orin NX).

## Lancement

```bash
cd /home/unitree/unitree_sdk2_python && python3.8 /home/unitree/g1_agent_interim/main.py
```

**Toujours lancer depuis `/home/unitree/unitree_sdk2_python`** — le SDK Unitree requiert ce répertoire de travail.

## Architecture

```
g1_agent_interim/
├── main.py                  # Point d'entrée : init hardware + lance les boucles async
├── config.py                # Clés API, URLs, voix, volumes, system prompt
├── agent/
│   ├── session.py           # Connexion WebSocket OpenAI Realtime + session.update
│   └── events.py            # Boucles async : envoi micro + réception events
├── robot/
│   ├── hardware.py          # Init ChannelFactory, AudioClient, G1ArmActionClient
│   ├── audio.py             # Détection micro USB, lecture audio PCM via ffmpeg
│   └── gestures.py          # execute_gesture() — map geste → code action bras
├── tools/
│   ├── registry.py          # register() / get_schemas() / call() — découverte centrale
│   ├── database.py          # Tool chercher_formation → Supabase table formation
│   ├── web_search.py        # Tool recherche_web → Serper API
│   └── gesture_tool.py      # Tool executer_geste → threading → robot/gestures.py
└── vision/
    └── __init__.py          # Réservé pour vision future (caméra)
```

## Stack technique

- **Python 3.8** — obligatoire (SDK Unitree incompatible avec versions supérieures)
- **OpenAI Realtime API** — `wss://api.openai.com/v1/realtime?model=gpt-realtime-2`
- **Supabase** — table `formation` (nom, prenom, typo, fpi, fphi, certif, carte_pro, badge_date_expiration)
- **Serper API** — recherche web
- **sounddevice** — capture micro USB (48000 Hz, downsample → 24000 avant envoi)
- **ffmpeg** — conversion PCM 24kHz → WAV 16kHz pour lecture sur robot

## Variables d'environnement

Chargées depuis `~/.env` :

```
OPENAI_API_KEY
SERPER_API_KEY
SUPABASE_URL
SUPABASE_SERVICE_KEY
```

## Réseau

- Jetson IP : 192.168.123.164
- Robot RockChip : 192.168.123.161
- Interface robot : `eth0` — Interface internet : `wlan0`
- Fix route manquante : `sudo ip route add default via 192.168.0.1 dev wlan0`
- Fix DNS : `echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf`
- Fix date après reboot : `sudo date -s "2026-05-28 10:00:00"`

## Hardware

| Composant | Détail |
|-----------|--------|
| Micro | USB Cubilux, détecté automatiquement par nom "USB", 48000 Hz |
| Haut-parleur | PlayStream via AudioClient SDK (channel `chat`) |
| Bras | G1ArmActionClient — actions : 25 saluer, 27 serrer_main, 19 calin, 17 applaudir, 99 reset |

## Tools OpenAI

Enregistrés via `tools/registry.py`. Les tools se self-enregistrent à l'import dans `main.py`.

| Tool | Fichier | Description |
|------|---------|-------------|
| `recherche_web` | tools/web_search.py | Recherche Serper, paramètre `query` |
| `chercher_formation` | tools/database.py | Recherche Supabase par nom, paramètre `nom` |
| `executer_geste` | tools/gesture_tool.py | Lance geste en thread daemon, paramètre `geste` |

## Events Realtime API (gpt-realtime-2)

| Event | Action |
|-------|--------|
| `input_audio_buffer.speech_started` | Stop lecture en cours si `responding` |
| `conversation.item.input_audio_transcription.completed` | Affiche transcript utilisateur |
| `response.output_audio.delta` | Accumule PCM dans `audio_buf` |
| `response.output_audio_transcript.delta` | Accumule texte dans `text_buf` |
| `response.output_audio.done` | Joue l'audio accumulé via `play_audio()` |
| `response.output_item.added` (function_call) | Capture `call_id` + `name` du tool |
| `response.function_call_arguments.done` | Dispatch vers `registry.call()`, renvoie résultat |

## Ajouter un nouveau tool

1. Créer `tools/mon_tool.py` avec une fonction `_handler(**args)` et appeler `register(schema, _handler)`
2. Importer le module dans `main.py` : `import tools.mon_tool  # noqa: F401`
