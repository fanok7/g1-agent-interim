from agent.parler_client import send_emotion
import json, base64, asyncio, os, time, threading
import sounddevice as sd
import numpy as np
from robot.audio import play_audio, find_microphone
from robot.hardware import get_audio_client
from robot.led_manager import led
from robot.gestures import execute_gesture
from tools.registry import call as call_tool
from tools.screenshot_tool import (send_image_email, FALL_RECIPIENT as _FALL_RECIPIENT,
                                   FIRE_RECIPIENT as _FIRE_RECIPIENT)

try:
    from tablet_server.server import push_chat, push_status
    _TABLET_AVAILABLE = True
except Exception:
    _TABLET_AVAILABLE = False

_RESPONDING_FLAG  = "/tmp/agent_responding"
_FACE_STATE_FILE  = "/tmp/face_id_state.json"
_FACE_STALE_SECS  = 5.0
_RPS_GO_SIGNAL    = "/tmp/rps_go"
_RPS_GO_LEAD      = 0.1   # avance (s) sur la fin du TTS — compense le mouvement des doigts
_FALL_STATE_FILE  = "/tmp/fall_state.json"
_FALL_STALE_SECS  = 15.0  # au-delà : résidu d'un crash, on ignore
_FIRE_STATE_FILE  = "/tmp/fire_state.json"
_FIRE_STALE_SECS  = 15.0
_QR_STATE_FILE    = "/tmp/qr_state.json"
_QR_STALE_SECS    = 15.0

# Tools qui nécessitent une instruction forcée dans response.create
_TOOL_INSTRUCTIONS = {
    'demarrer_pfc': 'Dis exactement et uniquement ce texte, mot pour mot, avec enthousiasme : "3 ! 2 ! 1 ! Go !"',
}

def _response_create(tool_name=None):
    msg = {'type': 'response.create'}
    led.reflechit() 
    if tool_name and tool_name in _TOOL_INSTRUCTIONS:
        msg['response'] = {'instructions': _TOOL_INSTRUCTIONS[tool_name]}
    return msg

def _set_responding(state: bool):
    if state:
        open(_RESPONDING_FLAG, 'w').close()
    else:
        try:
            os.remove(_RESPONDING_FLAG)
        except FileNotFoundError:
            pass


# ── Salut automatique garanti par le CODE ─────────────────────────────────────
# Le modèle (mini) est surchargé de contexte et oublie parfois d'appeler le geste.
# Dès que le robot DIT bonjour/au revoir, on lance le geste 'saluer' nous-mêmes —
# fiable quel que soit le contexte. Anti-doublon partagé avec face_greeting_loop.
_GREETING_WORDS = ('bonjour', 'bonsoir', 'coucou', 'bienvenue', 'salut',
                   'au revoir', 'au plaisir', 'bonne journée', 'à bientôt',
                   'à très vite', 'enchanté')
_CONGRATS_WORDS = ('félicitation', 'bravo', 'bien joué', 'chapeau', 'hourra',
                   'youpi', 'bonne nouvelle', 'quelle réussite', 'super nouvelle')
_last_gesture = {}              # geste → dernier timestamp (anti-doublon par geste)
_gesture_lock = threading.Lock()
_suppress_gestures_until = 0.0  # timestamp : gestes bloqués pendant scan billet


def _fire_gesture(geste: str, min_gap: float = 6.0) -> bool:
    """Lance un geste (thread), au plus une fois toutes les min_gap s par type de geste."""
    if time.time() < _suppress_gestures_until:
        return False
    with _gesture_lock:
        if time.time() - _last_gesture.get(geste, 0.0) < min_gap:
            return False
        _last_gesture[geste] = time.time()
    threading.Thread(target=execute_gesture, args=(geste,), daemon=True).start()
    return True


def _greet_now() -> bool:
    return _fire_gesture('saluer')


def _maybe_reflex_gesture(text: str):
    """Gestes réflexes garantis par le CODE (le modèle surchargé les oublie) :
    salut quand le robot dit bonjour/au revoir, applaudissements quand il félicite."""
    low = (text or '').lower()
    if any(w in low for w in _GREETING_WORDS):
        _fire_gesture('saluer')
    elif any(w in low for w in _CONGRATS_WORDS):
        _fire_gesture('applaudir')

MICRO_INDEX, MICRO_SR = find_microphone()


async def send_audio_loop(ws):
    loop = asyncio.get_event_loop()
    q = asyncio.Queue()

    def cb(indata, frames, t, status):
        data = indata[::2] if MICRO_SR == 48000 else indata
        pcm = (data * 32767).astype(np.int16).tobytes()
        loop.call_soon_threadsafe(q.put_nowait, pcm)

    with sd.InputStream(samplerate=MICRO_SR, channels=1, dtype='float32',
                        device=MICRO_INDEX, blocksize=int(MICRO_SR * 0.02),
                        callback=cb):
        while True:
            chunk = await q.get()
            if os.path.exists(_RESPONDING_FLAG):
                continue
            await ws.send(json.dumps({
                'type': 'input_audio_buffer.append',
                'audio': base64.b64encode(chunk).decode()
            }))


async def _flush_results(ws, results):
    """Envoie un batch de résultats de tools + un seul response.create.
    Si un tool du batch exige une instruction forcée (ex: compte à rebours PFC),
    elle est appliquée quelle que soit sa position dans le batch."""
    for cid, name, result in results:
        await ws.send(json.dumps({
            'type': 'conversation.item.create',
            'item': {'type': 'function_call_output', 'call_id': cid, 'output': result}
        }))
    forced = next((n for _, n, _ in results if n in _TOOL_INSTRUCTIONS), None)
    await ws.send(json.dumps(_response_create(forced)))
    return forced


async def receive_events_loop(ws):
    loop = asyncio.get_event_loop()

    audio_buf      = bytearray()
    text_buf       = ''
    responding     = False
    rps_go_pending = False
    _audio_playing = False   # True pendant que play_audio tourne dans l'executor

    # État multi-tools : keyed par call_id (corrige la corruption scalaire)
    _calls   = {}   # call_id → {'name': str, 'args': str}   — en cours de streaming
    _results = []   # [(call_id, name, result)]               — prêts, batch courant
    _queued  = []   # [(call_id, name, result)]               — différés (robot parlait)

    async for raw in ws:
        e = json.loads(raw)
        t = e.get('type', '')

        if t == 'input_audio_buffer.speech_started':
            print('[Toi] Parle...')
            if responding:
                get_audio_client().PlayStop('chat')
                audio_buf.clear()
                responding = False
                _set_responding(False)
                rps_go_pending = False

        elif t == 'conversation.item.input_audio_transcription.completed':
            transcript = e.get("transcript", "")
            print(f'[Toi] {transcript}')
            if _TABLET_AVAILABLE and transcript.strip():
                push_chat("user", transcript)
                push_status("reflechit")

        elif t == 'response.output_audio.delta':
            audio_buf.extend(base64.b64decode(e['delta']))
            if not responding:
                print('[G1] Parle...')
                _set_responding(True)
                send_emotion("parle")
                led.parle()
                if _TABLET_AVAILABLE:
                    push_status("parle")
            responding = True

        elif t == 'response.output_audio_transcript.delta':
            text_buf += e.get('delta', '')

        elif t == 'response.output_audio.done':
            if audio_buf:
                print(f'[G1] {text_buf}')
                if _TABLET_AVAILABLE and text_buf.strip():
                    push_chat("assistant", text_buf)
                _maybe_reflex_gesture(text_buf)   # salut/applaudissements auto par le code
                if rps_go_pending:
                    dur = len(audio_buf) / 2 / 24000.0
                    threading.Timer(max(0.0, dur - _RPS_GO_LEAD),
                                    lambda: open(_RPS_GO_SIGNAL, 'w').close()).start()
                    rps_go_pending = False
                pcm = bytes(audio_buf)
                audio_buf.clear()
                # _audio_playing positionné AVANT l'await : response.done peut
                # arriver pendant la lecture et ne touchera pas le flag.
                _audio_playing = True
                await loop.run_in_executor(None, play_audio, pcm)
                _audio_playing = False
                send_emotion("content")
                led.ecoute()
                if _TABLET_AVAILABLE:
                    push_status("ecoute")
                text_buf = ''
                responding = False
                _set_responding(False)
                print('[G1] Écoute...')

        elif t == 'response.done':
            # Ne pas retirer le flag si l'audio est encore en lecture :
            # play_audio dans l'executor s'en charge quand il termine.
            if not _audio_playing:
                responding = False
                _set_responding(False)

            to_send = _queued + _results
            _queued.clear()
            _results.clear()
            if to_send:
                forced = await _flush_results(ws, to_send)
                if forced == 'demarrer_pfc':
                    rps_go_pending = True

        elif t == 'response.output_item.added':
            item = e.get('item', {})
            if item.get('type') == 'function_call':
                cid  = item.get('call_id')
                name = item.get('name')
                _calls[cid] = {'name': name, 'args': ''}
                print(f'[TOOL] Appel : {name}')

        elif t == 'response.function_call_arguments.delta':
            cid = e.get('call_id')
            if cid in _calls:
                _calls[cid]['args'] += e.get('delta', '')

        elif t == 'response.function_call_arguments.done':
            cid = e.get('call_id')
            if cid not in _calls:
                continue
            entry = _calls.pop(cid)
            name  = entry['name']
            try:
                # L'event .done porte les arguments complets — plus fiable que
                # l'accumulation des deltas
                args = json.loads(e.get('arguments') or entry['args'] or '{}')
                print(f'[TOOL] Args : {args}')
                # Exécution dans un thread pool : ne bloque plus la boucle asyncio
                result = await loop.run_in_executor(
                    None, lambda n=name, a=args: call_tool(n, a)
                )
            except Exception as ex:
                print(f'[TOOL] Erreur : {ex}')
                result = str(ex)

            # Si le robot parle encore, différer ; sinon accumuler dans le batch courant.
            # Le flush réel se fait sur response.done, pas ici.
            if responding:
                _queued.append((cid, name, str(result)))
            else:
                _results.append((cid, name, str(result)))

        elif t == 'error':
            print(f'[ERREUR] {e.get("error", {})}')


async def rps_result_loop(ws):
    """Injecte le résultat RPS dans la conversation dès que la partie se termine."""
    _RPS_RESULT = '/tmp/rps_result.json'
    while True:
        await asyncio.sleep(1)
        if not os.path.exists(_RPS_RESULT):
            continue
        try:
            with open(_RPS_RESULT) as f:
                result = json.load(f)
            os.remove(_RPS_RESULT)
        except Exception:
            continue

        r      = result.get('result', 'rate')
        player = result.get('player') or 'inconnu'
        robot  = result.get('robot', '?')
        sp     = result.get('score_player', 0)
        sr     = result.get('score_robot', 0)

        # Attendre que le robot ait fini de parler avant d'injecter le résultat
        # (sinon response.create est rejeté et le résultat est perdu)
        for _ in range(30):
            if not os.path.exists(_RESPONDING_FLAG):
                break
            await asyncio.sleep(0.5)

        if r == 'rate':
            msg = (f'[RPS] Geste du joueur non détecté. '
                   f'Le robot avait joué {robot}. '
                   f'Annonce que tu n\'as pas vu son geste et propose de rejouer.')
        else:
            verdict = {
                'victoire': 'le joueur gagne, toi (le robot) tu as perdu',
                'defaite':  'toi (le robot) tu gagnes, le joueur a perdu',
                'egalite':  'égalité, personne ne gagne',
            }.get(r, r)
            msg = (f'[RPS] Toi (le robot) tu as joué {robot}, le joueur a joué {player}. '
                   f'Verdict : {verdict}. '
                   f'Score : joueur {sp} — robot {sr}. '
                   f'Annonce le résultat de façon enthousiaste et propose une revanche.')

        await ws.send(json.dumps({
            'type': 'conversation.item.create',
            'item': {
                'type':    'message',
                'role':    'user',
                'content': [{'type': 'input_text', 'text': msg}],
            }
        }))
        await ws.send(json.dumps({'type': 'response.create'}))


async def fall_alert_loop(ws):
    """Alerte proactive : détecte une chute via /tmp/fall_state.json (écrit par
    AgentToolHandler du module vision/fall_detection) et fait réagir le robot
    immédiatement. Consomme le fichier (lecture + suppression) — l'anti-spam
    (cooldown) est géré côté détecteur."""
    while True:
        await asyncio.sleep(1)
        if not os.path.exists(_FALL_STATE_FILE):
            continue
        try:
            with open(_FALL_STATE_FILE) as f:
                state = json.load(f)
            os.remove(_FALL_STATE_FILE)
        except (FileNotFoundError, json.JSONDecodeError):
            continue

        # Résidu d'un crash précédent : timestamp périmé → on ignore
        if time.time() - state.get('ts', 0) > _FALL_STALE_SECS:
            continue

        print('[FALL] Chute détectée → alerte proactive', flush=True)

        # Envoi de la photo de la chute par email (bloquant réseau → executor).
        # L'image a été sauvegardée par le module fall_detection dans vision/Screenshot.
        image_path = state.get('image')
        loop = asyncio.get_event_loop()
        sent = await loop.run_in_executor(
            None, lambda: send_image_email(
                image_path or '', _FALL_RECIPIENT,
                'ALERTE CHUTE — Homme à terre',
                'Le robot G1 a détecté une personne au sol. Photo en pièce jointe.'))
        print(f'[FALL] Email : {sent}', flush=True)

        # Une chute est urgente : on attend juste que le robot finisse sa phrase
        # en cours (sinon response.create est rejeté), au plus ~3s.
        for _ in range(6):
            if not os.path.exists(_RESPONDING_FLAG):
                break
            await asyncio.sleep(0.5)

        await ws.send(json.dumps({
            'type': 'conversation.item.create',
            'item': {
                'type': 'message',
                'role': 'user',
                'content': [{'type': 'input_text',
                             'text': '[SYSTÈME URGENT] La caméra vient de détecter une '
                                     'personne au sol (chute probable). Une photo a été '
                                     'envoyée par email pour prévenir les secours.'}]
            }
        }))
        # On force le cri d'alerte exact, puis le robot rassure.
        await ws.send(json.dumps({'type': 'response.create', 'response': {
            'instructions': 'Dis fort, avec urgence, exactement ces mots pour commencer : '
                            '"Homme à terre ! Homme à terre !" Puis, calmement, demande si la '
                            'personne va bien et indique que tu as prévenu quelqu\'un par email.'}}))
        await asyncio.sleep(5)


async def fire_alert_loop(ws):
    """Alerte proactive : détecte un feu/fumée via /tmp/fire_state.json (écrit par
    AgentToolHandler du module vision/fire_detection) et fait crier le robot
    immédiatement. Consomme le fichier (lecture + suppression) — l'anti-spam
    (cooldown) est géré côté détecteur. Calqué sur fall_alert_loop."""
    while True:
        await asyncio.sleep(1)
        if not os.path.exists(_FIRE_STATE_FILE):
            continue
        try:
            with open(_FIRE_STATE_FILE) as f:
                state = json.load(f)
            os.remove(_FIRE_STATE_FILE)
        except (FileNotFoundError, json.JSONDecodeError):
            continue

        # Résidu d'un crash précédent : timestamp périmé → on ignore
        if time.time() - state.get('ts', 0) > _FIRE_STALE_SECS:
            continue

        event = state.get('event', 'fire')   # 'fire' ou 'smoke'
        quoi  = 'de la fumée' if event == 'smoke' else 'un départ de feu'
        print(f'[FIRE] {event} détecté → alerte proactive', flush=True)

        # Envoi de la photo de la scène par email (bloquant réseau → executor).
        image_path = state.get('image')
        loop = asyncio.get_event_loop()
        sent = await loop.run_in_executor(
            None, lambda: send_image_email(
                image_path or '', _FIRE_RECIPIENT,
                'ALERTE FEU — Départ de feu détecté',
                f'Le robot G1 a détecté {quoi}. Photo en pièce jointe.'))
        print(f'[FIRE] Email : {sent}', flush=True)

        # Un feu est urgent : on attend juste que le robot finisse sa phrase
        # en cours (sinon response.create est rejeté), au plus ~3s.
        for _ in range(6):
            if not os.path.exists(_RESPONDING_FLAG):
                break
            await asyncio.sleep(0.5)

        await ws.send(json.dumps({
            'type': 'conversation.item.create',
            'item': {
                'type': 'message',
                'role': 'user',
                'content': [{'type': 'input_text',
                             'text': f'[SYSTÈME URGENT] La caméra vient de détecter {quoi} '
                                     '(incendie probable). Une photo a été envoyée par email '
                                     'pour prévenir les secours.'}]
            }
        }))
        # On force le cri d'alerte exact, puis le robot guide vers la sortie.
        await ws.send(json.dumps({'type': 'response.create', 'response': {
            'instructions': 'Dis fort, avec urgence, exactement ces mots pour commencer : '
                            '"Au feu ! Au feu !" Puis, calmement, demande aux personnes de '
                            's\'éloigner et d\'évacuer vers la sortie, et indique que tu as '
                            'prévenu quelqu\'un par email.'}}))
        await asyncio.sleep(5)


async def qr_alert_loop(ws):
    """Détecte les billets scannés passivement et les injecte dans la conversation."""
    while True:
        await asyncio.sleep(1)
        if not os.path.exists(_QR_STATE_FILE):
            continue
        try:
            with open(_QR_STATE_FILE) as f:
                state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if time.time() - state.get('ts', 0) > _QR_STALE_SECS:
            continue
        try:
            os.remove(_QR_STATE_FILE)
        except FileNotFoundError:
            pass
        for _ in range(30):
            if not os.path.exists(_RESPONDING_FLAG):
                break
            await asyncio.sleep(0.3)

        passager = state.get('passager', '')
        vol      = state.get('vol', '')
        de       = state.get('de', '')
        vers     = state.get('vers', '')
        pnr      = state.get('pnr', '')

        if passager:
            texte = (
                f"[SYSTÈME] Billet détecté automatiquement par la caméra. "
                f"Passager : {passager}. Vol : {vol}. De {de} vers {vers}. PNR : {pnr}. "
                f"Accueille le passager par son nom, confirme son vol et propose de l'aide."
            )
        else:
            texte = f"[SYSTÈME] Code QR scanné : {state.get('raw','')[:120]}"

        print(f'[QR] Billet injecté : {passager} / {vol}', flush=True)
        # Bloquer les gestes réflexes pendant la réponse QR (bras en mouvement = dangereux
        # quand quelqu'un tient son téléphone ou billet devant la caméra)
        global _suppress_gestures_until
        _suppress_gestures_until = time.time() + 15.0
        await ws.send(json.dumps({'type': 'conversation.item.create', 'item': {
            'type': 'message', 'role': 'user',
            'content': [{'type': 'input_text', 'text': texte}]
        }}))
        await ws.send(json.dumps({'type': 'response.create'}))
        await asyncio.sleep(3)


async def face_greeting_loop(ws):
    greeted              = set()
    # embeddings des inconnus déjà salués : liste de (vecteur np, timestamp)
    _greeted_unknowns: list = []
    # confirmation : inconnu_id → (embedding accumulé, count)
    _pending_unknowns: dict = {}
    UNKNOWN_SIM_THRESHOLD = 0.4   # même seuil qu'InsightFace — même personne si > 0.4
    UNKNOWN_FORGET_SEC    = 6000.0  # oublier un inconnu après 10 min (resaluer s'il revient)
    CONFIRM_FRAMES        = 3      # frames consécutives avant de saluer
    INCONNU_COOLDOWN      = 25.0  # cooldown post-conversation uniquement

    for _ in range(30):
        if os.path.exists(_FACE_STATE_FILE):
            break
        await asyncio.sleep(1)
    else:
        await asyncio.sleep(5)

    while True:
        await asyncio.sleep(1)

        # Bloquer si le robot parle ou réfléchit
        if os.path.exists(_RESPONDING_FLAG):
            continue

        # Cooldown post-conversation : pas de salutation pendant INCONNU_COOLDOWN
        # secondes après que le robot a fini de parler
        try:
            with open('/tmp/last_conversation_end') as f:
                _last_conversation_end = float(f.read().strip())
        except (FileNotFoundError, ValueError):
            _last_conversation_end = 0.0

        if time.time() - _last_conversation_end < INCONNU_COOLDOWN:
            continue

        try:
            with open(_FACE_STATE_FILE) as f:
                state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            continue

        if time.time() - state.get('ts', 0) > _FACE_STALE_SECS:
            continue

        for face in state.get('faces', []):
            name = face.get('name', 'Inconnu')

            # ── Personne connue ───────────────────────────────────────────────
            if name != 'Inconnu':
                if name in greeted:
                    continue
                greeted.add(name)
                led.visage_reconnu()                           # 💜 Violet
                threading.Timer(4.0, led.clear_vision).start()
                print(f'[FACE] Personne reconnue : {name} → salutation')
                _greet_now()
                await ws.send(json.dumps({
                    'type': 'conversation.item.create',
                    'item': {
                        'type': 'message', 'role': 'user',
                        'content': [{'type': 'input_text',
                                     'text': f'[SYSTÈME] La caméra vient de détecter {name}. '
                                             f'Salue-le chaleureusement par son prénom.'}]
                    }
                }))
                await ws.send(json.dumps({'type': 'response.create'}))
                await asyncio.sleep(5)

            # ── Inconnu ───────────────────────────────────────────────────────
            else:
                # Ignorer si le score est trop proche d'une personne connue
                score = face.get('score', 1.0)
                if score > 0.15:
                    continue

                # Récupérer l'embedding fourni par face_id.py
                emb_raw = face.get('embedding')
                if not emb_raw:
                    continue
                emb = np.array(emb_raw, dtype=np.float32)

                now = time.time()

                # Purger les inconnus oubliés (> UNKNOWN_FORGET_SEC)
                _greeted_unknowns[:] = [
                    (e, t) for (e, t) in _greeted_unknowns
                    if now - t < UNKNOWN_FORGET_SEC
                ]

                # Vérifier si cet inconnu a déjà été salué
                already_greeted = any(
                    float(np.dot(emb, e)) > UNKNOWN_SIM_THRESHOLD
                    for (e, _) in _greeted_unknowns
                )
                if already_greeted:
                    _pending_unknowns.pop('inconnu', None)
                    continue

                # Confirmation sur CONFIRM_FRAMES frames consécutives
                prev_emb, count = _pending_unknowns.get('inconnu', (emb, 0))
                # Vérifier que c'est bien la même personne entre frames
                if float(np.dot(emb, prev_emb)) > UNKNOWN_SIM_THRESHOLD:
                    count += 1
                else:
                    count = 1  # nouvelle tête différente, recommencer
                _pending_unknowns['inconnu'] = (emb, count)

                if count < CONFIRM_FRAMES:
                    continue

                # Confirmé → saluer + mémoriser + réinitialiser le compteur
                _pending_unknowns.pop('inconnu', None)
                _greeted_unknowns.append((emb, now))
                led.visage_inconnu()                           # 🩷 Magenta
                threading.Timer(4.0, led.clear_vision).start()
                print(f'[FACE] Nouvel inconnu confirmé ({CONFIRM_FRAMES} frames) → salutation')
                _greet_now()
                await ws.send(json.dumps({
                    'type': 'conversation.item.create',
                    'item': {
                        'type': 'message', 'role': 'user',
                        'content': [{'type': 'input_text',
                                     'text': '[SYSTÈME] La caméra vient de détecter une '
                                             'nouvelle personne inconnue devant toi. '
                                             'Dis-lui bonjour chaleureusement.'}]
                    }
                }))
                await ws.send(json.dumps({'type': 'response.create'}))
                await asyncio.sleep(5)