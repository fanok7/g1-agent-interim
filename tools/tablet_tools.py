"""
tools/tablet_tools.py — Outils d'affichage sur la tablette embarquée du robot.

La tablette n'a pas de cerveau à elle : le micro, le haut-parleur et l'IA de
conversation restent entièrement dans agent/events.py (API Realtime OpenAI).
Ces 4 tools ne font que piloter l'ÉCRAN annexe (texte/QR/plan/boutons), en
poussant vers tablet_server via Server-Sent Events.

Portés depuis g1_virtual_tablet (banc de test) — mêmes 4 outils, mêmes
comportements (synergie avec googlemaps_tools.py déjà présent dans ce
projet, donc pas de hack sys.path nécessaire ici contrairement au banc de
test qui vivait dans un projet séparé).
"""

import os
import socket
import time
from urllib.parse import quote

import qrcode

from tools.registry import register
from tools.googlemaps_tools import compute_route, geocode_address
from tablet_server.server import push_display, push_choices

_BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STATIC_DIR = os.path.join(_BASE_DIR, "tablet_server", "static")
_QR_DIR    = os.path.join(_STATIC_DIR, "qrcodes")
_PLANS_DIR = os.path.join(_STATIC_DIR, "plans")
_NOTES_DIR = os.path.join(_STATIC_DIR, "notes")

_TABLET_PORT = 8000


def _detect_lan_ip() -> str:
    """IP locale utilisée pour sortir vers Internet (le wifi/eth partagé) —
    sert à construire un lien LAN accessible depuis un téléphone sur le même
    réseau (fallback QR texte trop long pour tenir dans un seul QR direct)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _tablet_lan_url() -> str:
    return f"http://{_detect_lan_ip()}:{_TABLET_PORT}"


def _save_qr(data: str, out_dir: str, prefix: str, error_correction=qrcode.constants.ERROR_CORRECT_M) -> str:
    os.makedirs(out_dir, exist_ok=True)
    filename = f"{prefix}_{int(time.time() * 1000)}.png"
    filepath = os.path.join(out_dir, filename)
    qr = qrcode.QRCode(error_correction=error_correction)
    qr.add_data(data)
    qr.make(fit=True)
    qr.make_image().save(filepath)
    rel_dir = os.path.relpath(out_dir, _STATIC_DIR)
    return f"/static/{rel_dir}/{filename}"


# ── proposer_choix ───────────────────────────────────────────────────────────
def _proposer_choix_handler(options) -> str:
    push_choices(options)
    return f"Boutons tactiles affichés : {', '.join(options)}."


register(
    {
        "name": "proposer_choix",
        "description": (
            "Affiche des boutons tactiles sur la tablette correspondant EXACTEMENT "
            "aux options de la question fermée que tu viens de poser à l'oral — "
            "alternative tactile à une réponse vocale. Appelle TOUJOURS cet outil "
            "juste après avoir posé une question à choix fermé (oui/non, ou un choix "
            "parmi plusieurs options nommées), quel que soit le nombre d'options. "
            "Exemples : question oui/non -> options=['Oui','Non'] ; question sur le "
            "mode de transport -> options=['À pied','En voiture','En transport en "
            "commun','À vélo']. Libellés courts (1-3 mots), correspondant exactement "
            "à ce que l'utilisateur pourrait dire à l'oral."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 4,
                    "description": "2 à 4 libellés courts, un par bouton, dans l'ordre logique.",
                },
            },
            "required": ["options"],
        },
    },
    _proposer_choix_handler,
)


# ── afficher_texte_ecran ──────────────────────────────────────────────────────
def _save_text_retrieval_qr(titre, contenu_texte):
    try:
        url = _save_qr(contenu_texte, _QR_DIR, "qr", error_correction=qrcode.constants.ERROR_CORRECT_L)
        return url, "text"
    except (qrcode.exceptions.DataOverflowError, ValueError):
        os.makedirs(_NOTES_DIR, exist_ok=True)
        filename = f"note_{int(time.time() * 1000)}.txt"
        filepath = os.path.join(_NOTES_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"{titre}\n{'=' * len(titre)}\n\n{contenu_texte}\n")
        note_link = f"{_tablet_lan_url()}/static/notes/{filename}"
        url = _save_qr(note_link, _QR_DIR, "qr")
        return url, "link"


def _afficher_texte_ecran_handler(titre, contenu_texte) -> str:
    qr_url, qr_mode = _save_text_retrieval_qr(titre, contenu_texte)
    push_display({
        "type": "text", "titre": titre, "contenu": contenu_texte,
        "qr_url": qr_url, "qr_mode": qr_mode,
    })
    return f"Texte affiché à l'écran : '{titre}' (QR de récupération : {qr_mode})."


register(
    {
        "name": "afficher_texte_ecran",
        "description": (
            "Affiche un texte formaté (titre + contenu) en plein écran sur la "
            "tablette du robot, accompagné d'un QR code permettant de récupérer ce "
            "texte directement sur le téléphone de l'utilisateur (scan -> texte "
            "copiable, aucun réseau requis). À utiliser uniquement après confirmation "
            "explicite de l'utilisateur, pour une information textuelle dense (listes, "
            "horaires, résultats multiples)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "titre": {"type": "string", "description": "Titre court affiché en haut de l'écran."},
                "contenu_texte": {
                    "type": "string",
                    "description": "Contenu à afficher, déjà mis en forme (retours à la ligne explicites si besoin).",
                },
            },
            "required": ["titre", "contenu_texte"],
        },
    },
    _afficher_texte_ecran_handler,
)


# ── afficher_qr_ecran ─────────────────────────────────────────────────────────
def _afficher_qr_ecran_handler(titre, donnee_a_encoder) -> str:
    image_url = _save_qr(donnee_a_encoder, _QR_DIR, "qr")
    push_display({"type": "qr", "titre": titre, "image_url": image_url})
    return f"QR code affiché à l'écran : '{titre}'."


register(
    {
        "name": "afficher_qr_ecran",
        "description": (
            "Génère et affiche un QR code générique en plein écran sur la tablette "
            "du robot (un lien, un texte à récupérer, etc.). À utiliser uniquement "
            "après confirmation explicite de l'utilisateur. Pour un itinéraire entre "
            "deux lieux nommés, préfère afficher_plan_ecran qui montre une vraie carte. "
            "Pour une info qui est fondamentalement du texte à lire, préfère "
            "afficher_texte_ecran."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "titre": {"type": "string", "description": "Titre court affiché au-dessus du QR code."},
                "donnee_a_encoder": {"type": "string", "description": "Donnée à encoder dans le QR code (URL, texte, etc.)."},
            },
            "required": ["titre", "donnee_a_encoder"],
        },
    },
    _afficher_qr_ecran_handler,
)


# ── afficher_plan_ecran ───────────────────────────────────────────────────────
_VALID_MODES = {"driving", "walking", "transit", "bicycling"}
_MODE_TO_ROUTES_API = {"driving": "DRIVE", "walking": "WALK", "transit": "TRANSIT", "bicycling": "BICYCLE"}


def _afficher_plan_ecran_handler(titre, origine, destination, mode) -> str:
    if mode not in _VALID_MODES:
        return f"[ERREUR] mode invalide '{mode}' — attendu : {', '.join(sorted(_VALID_MODES))}."

    geo_origine = geocode_address(origine)
    if "error" in geo_origine:
        return (
            f"[ERREUR] Lieu de départ introuvable : '{origine}' ({geo_origine['error']}). "
            f"Redemande à l'utilisateur un lieu plus précis (ville, quartier)."
        )
    geo_dest = geocode_address(destination)
    if "error" in geo_dest:
        return (
            f"[ERREUR] Lieu d'arrivée introuvable : '{destination}' ({geo_dest['error']}). "
            f"Redemande à l'utilisateur un lieu plus précis (ville, quartier)."
        )

    route = compute_route(
        origin_lat=geo_origine["location"]["lat"], origin_lng=geo_origine["location"]["lng"],
        dest_lat=geo_dest["location"]["lat"], dest_lng=geo_dest["location"]["lng"],
        travel_mode=_MODE_TO_ROUTES_API[mode],
    )
    if "error" in route:
        return (
            f"[ERREUR] Itinéraire introuvable entre '{origine}' et '{destination}' en mode "
            f"{mode} ({route['error']}). Redemande un autre mode de transport ou des lieux plus précis."
        )

    import requests
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    lat_o, lng_o = geo_origine["location"]["lat"], geo_origine["location"]["lng"]
    lat_d, lng_d = geo_dest["location"]["lat"], geo_dest["location"]["lng"]
    static_map = requests.get(
        "https://maps.googleapis.com/maps/api/staticmap",
        params={
            "size": "640x640",
            "markers": [f"color:green|label:A|{lat_o},{lng_o}", f"color:red|label:B|{lat_d},{lng_d}"],
            "key": api_key,
        },
        timeout=8,
    )
    if static_map.status_code != 200:
        return f"[ERREUR] Génération de la carte échouée (HTTP {static_map.status_code})."

    os.makedirs(_PLANS_DIR, exist_ok=True)
    filename = f"plan_{int(time.time() * 1000)}.png"
    with open(os.path.join(_PLANS_DIR, filename), "wb") as f:
        f.write(static_map.content)

    image_url = f"/static/plans/{filename}"
    gmaps_link = (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={lat_o},{lng_o}&destination={lat_d},{lng_d}&travelmode={mode}"
    )
    qr_url = _save_qr(gmaps_link, _QR_DIR, "qr")

    push_display({"type": "plan", "titre": titre, "image_url": image_url, "qr_url": qr_url})

    duration_s = route.get("duration", "").rstrip("s") or "?"
    distance_km = round(route.get("distance_meters", 0) / 1000, 1)
    return (
        f"Carte affichée à l'écran : '{titre}' (itinéraire {origine} → {destination}, "
        f"mode={mode}, {distance_km} km, ~{duration_s}s)."
    )


register(
    {
        "name": "afficher_plan_ecran",
        "description": (
            "Affiche une vraie carte avec deux marqueurs (départ/arrivée), accompagnée "
            "d'un QR code Google Maps navigable. À utiliser uniquement après confirmation "
            "explicite de l'utilisateur, pour un itinéraire entre deux lieux nommés."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "titre": {"type": "string", "description": "Titre court affiché au-dessus de la carte."},
                "origine": {
                    "type": "string",
                    "description": "Point de départ (adresse ou nom de lieu). Si non précisé, utiliser la position connue du robot.",
                },
                "destination": {"type": "string", "description": "Point d'arrivée (adresse ou nom de lieu)."},
                "mode": {
                    "type": "string",
                    "enum": ["driving", "walking", "transit", "bicycling"],
                    "description": (
                        "Mode de transport. Doit TOUJOURS être demandé à l'utilisateur avant "
                        "l'appel si non précisé — ne jamais deviner (driving=voiture, "
                        "walking=à pied, transit=transport en commun, bicycling=vélo)."
                    ),
                },
            },
            "required": ["titre", "origine", "destination", "mode"],
        },
    },
    _afficher_plan_ecran_handler,
)
