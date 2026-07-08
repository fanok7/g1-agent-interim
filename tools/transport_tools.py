"""Transport Île-de-France — geroTransport API v2."""

import json
from datetime import datetime

import httpx
import pytz
from tools.registry import register

_PARIS = pytz.timezone("Europe/Paris")

_BASE_URL = "http://10.75.1.20:8001"
_client   = httpx.Client(timeout=10.0, base_url=_BASE_URL)


def _get(path: str, params: dict = None) -> dict:
    response = _client.get(path, params=params or {})
    print(f"[TRANSPORT] GET {response.request.url} → {response.status_code}", flush=True)
    if not response.is_success:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
    return response.json()


def _post(path: str, body: dict) -> dict:
    response = _client.post(path, json=body)
    print(f"[TRANSPORT] POST {response.request.url} {body} → {response.status_code}", flush=True)
    if not response.is_success:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
    return response.json()


def prochains_departs_arret(stop: str) -> str:
    """Prochains départs depuis un arrêt (nom libre, résolution auto)."""
    try:
        data = _get("/llm/next", {"stop": stop})
        # Ancre temporelle : sans elle le LLM annonce des trains déjà passés.
        data["now"] = datetime.now(_PARIS).strftime("%H:%M")
        return json.dumps(data, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


def calculer_itineraire(from_name: str, to_name: str) -> str:
    """Itinéraire en transport en commun entre deux lieux (noms libres)."""
    try:
        return json.dumps(_get("/llm/journey", {"from_name": from_name, "to_name": to_name}), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


def etat_trafic_idf() -> str:
    """Perturbations et état du trafic en temps réel en IDF."""
    try:
        return json.dumps(_get("/llm/traffic"), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


def velib_a_proximite(name: str, limit: int = 3) -> str:
    """Stations Vélib' les plus proches d'un lieu (nom libre)."""
    try:
        return json.dumps(_get("/llm/velib/nearby", {"name": name, "limit": limit}), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


def itineraire_velo(from_name: str, to_name: str) -> str:
    """Itinéraire vélo entre deux lieux (noms libres, via Géovelo)."""
    try:
        return json.dumps(_post("/transport/bike/search", {"from_name": from_name, "to_name": to_name}), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


# --- Schemas ---

register(
    schema={
        "name": "prochains_departs_arret",
        "description": (
            "Donne les prochains départs de transport en commun (RER, Bus, Métro, Tramway) "
            "depuis un arrêt en Île-de-France. Accepte un nom libre (ex: 'Gare du Nord', 'CDG Terminal 2')."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "stop": {
                    "type": "string",
                    "description": "Nom de l'arrêt ou du lieu (ex: 'Nation', 'Aéroport CDG 2')"
                }
            },
            "required": ["stop"]
        }
    },
    handler=lambda **kw: prochains_departs_arret(**kw)
)

register(
    schema={
        "name": "calculer_itineraire",
        "description": (
            "Calcule l'itinéraire optimal en transport en commun entre deux lieux en Île-de-France. "
            "Accepte des noms de lieux libres."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "from_name": {
                    "type": "string",
                    "description": "Lieu de départ (ex: 'Nation', 'CDG Terminal 2')"
                },
                "to_name": {
                    "type": "string",
                    "description": "Lieu d'arrivée (ex: 'Châtelet', 'Gare de Lyon')"
                }
            },
            "required": ["from_name", "to_name"]
        }
    },
    handler=lambda **kw: calculer_itineraire(**kw)
)

register(
    schema={
        "name": "etat_trafic_idf",
        "description": (
            "Retourne l'état du trafic et les perturbations en cours sur le réseau "
            "de transport en commun d'Île-de-France (RER, Métro, Bus, Tramway)."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    handler=lambda **kw: etat_trafic_idf()
)

register(
    schema={
        "name": "velib_a_proximite",
        "description": "Trouve les stations Vélib' disponibles les plus proches d'un lieu en IDF.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nom du lieu (ex: 'Bastille', 'Opéra')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Nombre de stations à retourner (défaut: 3)"
                }
            },
            "required": ["name"]
        }
    },
    handler=lambda **kw: velib_a_proximite(**kw)
)

register(
    schema={
        "name": "itineraire_velo",
        "description": "Calcule un itinéraire cyclable entre deux lieux en IDF via Géovelo.",
        "parameters": {
            "type": "object",
            "properties": {
                "from_name": {
                    "type": "string",
                    "description": "Lieu de départ (ex: 'Nation')"
                },
                "to_name": {
                    "type": "string",
                    "description": "Lieu d'arrivée (ex: 'Bastille')"
                }
            },
            "required": ["from_name", "to_name"]
        }
    },
    handler=lambda **kw: itineraire_velo(**kw)
)
