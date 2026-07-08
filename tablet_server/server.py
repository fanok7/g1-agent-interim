"""
tablet_server/server.py — "Tablette virtuelle" du robot G1 (production).

Adapté depuis g1_virtual_tablet (banc de test) pour tourner en Python 3.8
(SDK Unitree oblige) — annotations de type via `typing` au lieu de `list[...]`
/ `X | None` (syntaxe Python 3.9+ uniquement).

Sert une page HTML unique qui se met à jour en temps réel via Server-Sent
Events (SSE), sans jamais recharger la page. Le backend pousse trois choses
indépendamment, appelées depuis agent/events.py au fil de la vraie
conversation (micro + haut-parleur du robot, API Realtime OpenAI) :
  - push_display() : le contenu de l'écran (texte/qr/plan/idle), déclenché
    par les tools tablette (tools/tablet_tools.py).
  - push_status()  : l'indicateur d'état du robot (écoute/réfléchit/parle).
  - push_chat()    : bulle de conversation (sous-titre utilisateur / réponse
    du robot), pour l'affichage façon chat en plus de la voix.

Le serveur tourne dans un thread séparé (uvicorn) démarré par main.py — la
communication avec le reste de l'agent (boucle asyncio de events.py) se fait
via loop.call_soon_threadsafe.
"""

import asyncio
import json
import os
import queue as _queue_mod
from typing import List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="G1 Tablette")
app.mount("/static", StaticFiles(directory=os.path.join(_BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_BASE_DIR, "templates"))

# ── État courant + abonnés SSE ──────────────────────────────────────────────
_current_state = {"type": "idle"}
_current_status = "ecoute"
_current_choices = []  # type: List[str]
_chat_history = []     # type: List[dict]   [{"role": "user"|"assistant", "text": "..."}, ...]
_CHAT_HISTORY_MAX = 50
_subscribers = []       # type: List[asyncio.Queue]
_loop = None            # type: Optional[asyncio.AbstractEventLoop]

# File d'attente thread-safe : réservée pour une évolution future (réponse
# tactile déclenchant une action côté agent) — non utilisée pour l'instant
# côté production, le robot n'a que le micro comme entrée.
input_queue = _queue_mod.Queue()


@app.on_event("startup")
async def _on_startup():
    global _loop
    _loop = asyncio.get_running_loop()


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request, "index.html",
        {
            "initial_state": json.dumps(_current_state),
            "initial_status": json.dumps(_current_status),
            "initial_choices": json.dumps(_current_choices),
            "initial_chat": json.dumps(_chat_history),
        },
    )


@app.get("/events")
async def events():
    """Flux SSE : chaque nouvel état (affichage, statut, choix, chat) est
    envoyé immédiatement à tous les clients connectés. Chaque message est une
    enveloppe {"display": {...}} / {"status": "..."} / {"choices": [...]} /
    {"chat": {...}} — le JS distingue selon la clé présente."""
    queue = asyncio.Queue()  # type: asyncio.Queue
    _subscribers.append(queue)

    async def stream():
        try:
            yield f"data: {json.dumps({'display': _current_state})}\n\n"
            yield f"data: {json.dumps({'status': _current_status})}\n\n"
            yield f"data: {json.dumps({'choices': _current_choices})}\n\n"
            while True:
                data = await queue.get()
                yield f"data: {data}\n\n"
        finally:
            _subscribers.remove(queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/respond")
async def respond(request: Request):
    """Réservé pour une future entrée tactile côté tablette (non utilisé par
    le robot réel pour l'instant — le micro est la seule entrée)."""
    body = await request.json()
    text = (body.get("text") or "").strip()
    if text:
        input_queue.put(text)
    return {"ok": True}


def _broadcast(envelope):
    data = json.dumps(envelope)
    if _loop is None:
        return
    for queue in list(_subscribers):
        _loop.call_soon_threadsafe(queue.put_nowait, data)


def push_display(payload):
    """Appelée par les tools tablette, potentiellement depuis un thread
    différent de celui du serveur uvicorn."""
    global _current_state
    _current_state = payload
    _broadcast({"display": payload})


def push_status(status):
    """Met à jour l'indicateur d'état du robot : 'ecoute', 'reflechit' ou
    'parle'. Appelée par agent/events.py au fil des events Realtime API."""
    global _current_status
    _current_status = status
    _broadcast({"status": status})


def push_choices(options):
    """Affiche des boutons tactiles sur la tablette, un par option — appelée
    par le tool proposer_choix() quand le LLM pose une question fermée."""
    global _current_choices
    _current_choices = list(options)
    _broadcast({"choices": _current_choices})


def push_chat(role, text):
    """Ajoute une bulle à la conversation affichée sur la tablette (rôle
    'user' ou 'assistant'). Appelée par agent/events.py avec exactement le
    texte transcrit du micro / le texte réellement prononcé par le robot."""
    entry = {"role": role, "text": text}
    _chat_history.append(entry)
    del _chat_history[:-_CHAT_HISTORY_MAX]
    _broadcast({"chat": entry})
