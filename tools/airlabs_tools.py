"""Airlabs API tools — HTTP client, tool functions, and OpenAI schemas in one place."""

import json
import os
from typing import Callable, Optional
import httpx

# --- HTTP client ---

_BASE_URL = "https://airlabs.co/api/v9"


class AirlabsError(Exception):
    pass


def _api_key() -> str:
    key = os.environ.get("AIRLABS_API_KEY", "")
    if not key:
        raise RuntimeError("AIRLABS_API_KEY is not set")
    return key


def _get(path: str, params: dict) -> dict:
    params["api_key"] = _api_key()
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(f"{_BASE_URL}{path}", params=params)
    except httpx.HTTPError as e:
        # Erreur RÉSEAU (timeout, DNS, connexion) — fréquent si le wifi du robot
        # a un micro-décrochage. On la convertit en AirlabsError (attrapée par les
        # tools) et on la LOGGUE pour pouvoir diagnostiquer depuis le terminal.
        print(f"[AIRLABS] réseau KO sur {path} : {e}", flush=True)
        raise AirlabsError(f"réseau indisponible : {e}")
    if not response.is_success:
        print(f"[AIRLABS] HTTP {response.status_code} sur {path} : {response.text[:200]}", flush=True)
        raise AirlabsError(f"HTTP {response.status_code}: {response.text[:200]}")
    data = response.json()
    if "error" in data:
        print(f"[AIRLABS] erreur API sur {path} : {data['error']}", flush=True)
        raise AirlabsError(data["error"].get("message", str(data["error"])))
    return data


def _fetch_airport(iata_code: str) -> Optional[dict]:
    data = _get("/airports", {"iata_code": iata_code})
    results = data.get("response", [])
    return results[0] if results else None


def _fetch_schedules(*, dep_iata: Optional[str] = None, arr_iata: Optional[str] = None,
                     limit: int = 50, status: Optional[str] = None,
                     airline_iata: Optional[str] = None) -> list:
    params: dict = {"limit": limit}
    if dep_iata:
        params["dep_iata"] = dep_iata
    if arr_iata:
        params["arr_iata"] = arr_iata
    if status:
        params["status"] = status
    if airline_iata:
        params["airline_iata"] = airline_iata
    return _get("/schedules", params).get("response", [])


# Grandes compagnies présentes à CDG — sert à reconstituer la journée complète en
# fusionnant une requête par compagnie (l'API plafonne à 100 vols et ne pagine pas).
_MAJOR_AIRLINES = [
    "AF", "DL", "KL", "LH", "BA", "AZ", "IB", "EK", "QR", "UA", "AA", "TK",
    "SK", "LX", "EW", "U2", "VY", "TP", "SN", "AT", "MS", "ET", "SU", "CA",
]


def _fetch_day_board(*, dep_iata: Optional[str] = None, arr_iata: Optional[str] = None) -> list:
    """Reconstitue les vols programmés de TOUTE la journée en fusionnant une requête
    scheduled par compagnie (l'API plafonne à 100 vols/requête, sans pagination).
    Plus coûteux (plusieurs appels parallèles) mais permet de voir n'importe quelle
    heure. Tolérant : une compagnie en erreur est ignorée."""
    import concurrent.futures

    def one(al):
        try:
            return _fetch_schedules(dep_iata=dep_iata, arr_iata=arr_iata,
                                    limit=100, status="scheduled", airline_iata=al)
        except Exception:
            return []

    merged: dict = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        for fl in ex.map(one, _MAJOR_AIRLINES):
            for f in fl:
                merged[f.get("flight_iata")] = f
    # Repli : si tout a échoué, au moins le tableau proche
    if not merged:
        return _fetch_board(dep_iata=dep_iata, arr_iata=arr_iata)
    return list(merged.values())


def _fetch_board(*, dep_iata: Optional[str] = None, arr_iata: Optional[str] = None) -> list:
    """Tableau d'affichage = vols À VENIR. On filtre par statut, sinon le plafond de
    100 résultats de l'API (saturé par les vols déjà partis, triés du plus ancien) ne
    laisse jamais voir l'heure courante.
      - DÉPARTS : status=scheduled (vols pas encore partis).
      - ARRIVÉES : les vols imminents sont EN VOL (status=active), les suivants
        'scheduled' → on fusionne les deux, sinon les avions en approche manquent.
    Repli sans filtre si tout est vide."""
    if arr_iata and not dep_iata:
        merged: dict = {}
        for st in ("active", "scheduled"):
            for f in _fetch_schedules(arr_iata=arr_iata, limit=100, status=st):
                merged[f.get("flight_iata")] = f
        if merged:
            return list(merged.values())
        return _fetch_schedules(arr_iata=arr_iata, limit=100)

    flights = _fetch_schedules(dep_iata=dep_iata, arr_iata=arr_iata, limit=100, status="scheduled")
    if not flights:
        flights = _fetch_schedules(dep_iata=dep_iata, arr_iata=arr_iata, limit=100)
    return flights


def _fetch_live_flights(*, dep_iata: Optional[str] = None, arr_iata: Optional[str] = None) -> list:
    params: dict = {}
    if dep_iata:
        params["dep_iata"] = dep_iata
    if arr_iata:
        params["arr_iata"] = arr_iata
    return _get("/flights", params).get("response", [])


def _fetch_flight(flight_iata: str) -> Optional[dict]:
    data = _get("/flight", {"flight_iata": flight_iata})
    response = data.get("response")
    if isinstance(response, list):
        return response[0] if response else None
    return response or None


def _fetch_delays(*, dep_iata: Optional[str] = None, arr_iata: Optional[str] = None,
                  delay: int = 30, flight_type: str = "departures") -> list:
    params: dict = {"delay": max(30, delay), "type": flight_type}
    if dep_iata:
        params["dep_iata"] = dep_iata
    if arr_iata:
        params["arr_iata"] = arr_iata
    return _get("/delays", params).get("response", [])


def _fetch_airline(iata_code: str) -> Optional[dict]:
    data = _get("/airlines", {"iata_code": iata_code})
    results = data.get("response", [])
    return results[0] if results else None


# --- field selectors ---

_SCHEDULE_KEYS = (
    "flight_iata", "airline_iata", "cs_airline_iata", "cs_flight_iata",
    "dep_iata", "arr_iata",
    "dep_time", "dep_estimated", "dep_actual",
    "arr_time", "arr_estimated", "arr_actual",
    "dep_terminal", "dep_gate",
    "arr_terminal", "arr_gate", "arr_baggage",
    "duration", "dep_delayed", "arr_delayed", "status",
)

_FLIGHT_KEYS = (
    "flight_iata", "airline_iata", "cs_airline_iata", "cs_flight_iata",
    "dep_iata", "arr_iata",
    "dep_time", "dep_estimated", "dep_actual",
    "arr_time", "arr_estimated", "arr_actual",
    "dep_terminal", "dep_gate",
    "arr_terminal", "arr_gate", "arr_baggage",
    "duration", "dep_delayed", "arr_delayed", "status",
    "lat", "lng", "alt", "dir", "speed", "v_speed",
    "reg_number", "aircraft_icao", "model", "manufacturer",
    "type", "engine", "engine_count", "built", "age",
    "updated",
)

_LIVE_KEYS = (
    "flight_iata", "airline_iata",
    "dep_iata", "arr_iata",
    "lat", "lng", "alt", "dir", "speed", "v_speed",
    "reg_number", "aircraft_icao",
    "status", "updated",
)

_DELAY_KEYS = (
    "flight_iata", "airline_iata",
    "dep_iata", "arr_iata",
    "dep_time", "dep_estimated",
    "arr_time", "arr_estimated",
    "dep_terminal", "dep_gate",
    "arr_terminal", "arr_gate",
    "dep_delayed", "arr_delayed", "status",
)

_AIRPORT_KEYS = (
    "iata_code", "name", "city", "country_code", "timezone",
    "lat", "lng", "alt", "runways", "departures", "connections",
    "is_major", "is_international",
)

_AIRLINE_KEYS = (
    "iata_code", "name", "country_code",
    "is_scheduled", "is_passenger", "is_cargo", "is_international",
    "total_aircrafts", "average_fleet_age",
    "accidents_last_5y", "crashes_last_5y",
)


def _pick(d: dict, keys: tuple) -> dict:
    return {k: d[k] for k in keys if k in d}


def _hm(value) -> Optional[str]:
    """'2026-06-15 08:25' → '08:25'. Renvoie None si vide."""
    if not value:
        return None
    s = str(value)
    return s.split(" ", 1)[1] if " " in s else s


def _drop_none(d: dict) -> dict:
    """Enlève les champs None/vides pour une sortie compacte et lisible."""
    return {k: v for k, v in d.items() if v not in (None, "", [])}


# Portes valides par terminal à CDG (2E = halls K/L/M). Sert à écarter les portes
# incohérentes renvoyées parfois par Airlabs (ex: terminal 2B + porte D66).
_CDG_TERMINAL_GATES = {
    "2A": {"A"}, "2B": {"B"}, "2C": {"C"}, "2D": {"D"},
    "2E": {"K", "L", "M"}, "2F": {"F"}, "2G": {"G"},
}


def _gate_consistent(terminal, gate) -> bool:
    """À CDG, la 1re lettre de la porte doit correspondre au terminal. Renvoie True
    si cohérent OU si on ne peut pas juger (porte numérique, terminal 1/3, autre aéroport)."""
    if not terminal or not gate:
        return True
    t = str(terminal).upper().replace(" ", "")
    g = str(gate).upper().strip()
    allowed = _CDG_TERMINAL_GATES.get(t)
    if not allowed or not g or not g[0].isalpha():
        return True
    return g[0] in allowed


def _summary_departure(f: dict) -> dict:
    """Sortie compacte d'un départ : seulement ce qui sert à renseigner un passager.
    'destination' reste un code IATA (ex: FRA) — l'agent dit le nom de la ville."""
    gate = f.get("dep_gate")
    if not _gate_consistent(f.get("dep_terminal"), gate):
        gate = None   # porte incohérente avec le terminal → on préfère ne rien dire
    return _drop_none({
        "vol":         f.get("flight_iata"),
        "destination": f.get("arr_iata"),
        "heure":       _hm(f.get("dep_time")),
        "heure_reelle": _hm(f.get("dep_estimated")) if f.get("dep_estimated") not in (None, f.get("dep_time")) else None,
        "terminal":    f.get("dep_terminal"),
        "porte":       gate,
        "retard_min":  f.get("dep_delayed"),
        "statut":      f.get("status"),
    })


def _summary_arrival(f: dict) -> dict:
    """Sortie compacte d'une arrivée. 'provenance' = code IATA (l'agent dit la ville).
    'heure' = heure d'arrivée RÉELLE attendue (estimée si dispo, sinon prévue) : c'est
    ce qui compte pour qui attend l'avion. 'heure_prevue' n'apparaît que si retard.
    Une arrivée n'a pas de porte d'embarquement : on donne le terminal et le tapis bagages."""
    sched = _hm(f.get("arr_time"))
    est   = _hm(f.get("arr_estimated"))
    heure = est or sched
    return _drop_none({
        "vol":          f.get("flight_iata"),
        "provenance":   f.get("dep_iata"),
        "heure":        heure,
        "heure_prevue": sched if (est and est != sched) else None,
        "terminal":     f.get("arr_terminal"),
        "tapis_bagages": f.get("arr_baggage"),
        "retard_min":   f.get("arr_delayed"),
        "statut":       f.get("status"),
    })


def _norm_terminal(value) -> str:
    """Normalise un libellé de terminal pour comparaison ('Terminal 2 F' → '2F')."""
    return str(value or "").upper().replace("TERMINAL", "").replace(" ", "").strip()


def _parse_dt(value):
    """'2026-06-15 08:25' → datetime naïf, ou None si illisible."""
    try:
        from datetime import datetime
        return datetime.strptime(str(value)[:16], "%Y-%m-%d %H:%M")
    except Exception:
        return None


def _now_paris():
    try:
        from tools.datetime_tool import maintenant_paris
        return maintenant_paris().replace(tzinfo=None)
    except Exception:
        from datetime import datetime
        return datetime.now()


def _parse_hour(value):
    """'14', '14:00', '14h', '14h30' → datetime AUJOURD'HUI à cette heure (Paris)."""
    if not value:
        return None
    import re
    m = re.match(r'\s*(\d{1,2})\s*[:hH]?\s*(\d{2})?', str(value))
    if not m:
        return None
    h = int(m.group(1))
    mn = int(m.group(2)) if m.group(2) else 0
    if not (0 <= h <= 23 and 0 <= mn <= 59):
        return None
    return _now_paris().replace(hour=h, minute=mn, second=0, microsecond=0)


def _max_time(flights: list, time_key: str):
    """Heure 'HH:MM' du vol le plus tardif disponible dans la liste (ou None)."""
    ts = [_parse_dt(f.get(time_key)) for f in flights]
    ts = [t for t in ts if t is not None]
    return max(ts).strftime("%H:%M") if ts else None


def _covers(flights: list, time_key: str, cutoff) -> bool:
    """True si la liste contient au moins un vol à/après l'heure demandée."""
    ts = [_parse_dt(f.get(time_key)) for f in flights]
    ts = [t for t in ts if t is not None]
    return bool(ts) and max(ts) >= cutoff


def _order_by_time(flights: list, time_key: str, cutoff=None, est_key=None) -> list:
    """Trie les vols par heure RÉELLE attendue. Garde ceux à/après une référence :
      - cutoff fourni (ex: 'à partir de 14h') → on garde >= cutoff, et rien d'autre ;
      - sinon → on garde les vols à venir (>= maintenant - 15 min), et s'il n'y en a
        aucun (données Airlabs en différé) on renvoie les plus RÉCENTS d'abord.
    est_key (ex: 'arr_estimated') : si fourni, on trie/filtre sur l'heure estimée
    quand elle existe (un vol retardé compte à son heure réelle, pas prévue)."""
    from datetime import timedelta
    now = _now_paris()
    ref = cutoff if cutoff is not None else (now - timedelta(minutes=15))

    def ftime(f):
        if est_key:
            t = _parse_dt(f.get(est_key))
            if t is not None:
                return t
        return _parse_dt(f.get(time_key))

    dated, nodate = [], []
    for f in flights:
        t = ftime(f)
        (dated if t is not None else nodate).append((f, t))

    upcoming = sorted([p for p in dated if p[1] >= ref], key=lambda p: p[1])
    if upcoming:
        return [f for f, _ in upcoming] + [f for f, _ in nodate]
    if cutoff is not None:
        # "à partir de X" demandé mais aucun vol à/après cette heure dans les données
        return []
    ordered = sorted(dated, key=lambda p: p[1], reverse=True)  # board général : plus récents
    return [f for f, _ in ordered] + [f for f, _ in nodate]


def _dedupe_codeshares(flights: list) -> list:
    """Regroupe les vols en partage de code (codeshare) : un même avion physique
    vendu sous plusieurs numéros de vol/compagnies. Airlabs donne pour chaque
    codeshare un champ cs_flight_iata pointant vers le vol opérant réel.
    On ne garde qu'UN vol par vol opérant — sinon l'agent récite 5x la même
    destination (ex: 5 vols 'Genève' à la même heure, même porte)."""
    chosen: dict = {}
    order: list = []
    for f in flights:
        op = f.get("cs_flight_iata") or f.get("flight_iata")
        if op not in chosen:
            chosen[op] = f
            order.append(op)
        elif not f.get("cs_flight_iata") and chosen[op].get("cs_flight_iata"):
            # f est le vol opérant (pas un codeshare) → on le préfère au codeshare
            chosen[op] = f
    # On affiche TOUJOURS le numéro du vol opérant (la clé 'op'), jamais celui d'un
    # codeshare : un vol opéré par Air France est annoncé "AF1640", même si on n'a
    # récupéré que sa version KLM/Delta. (copie pour ne pas muter l'original)
    result = []
    for op in order:
        f = dict(chosen[op])
        f["flight_iata"] = op
        if op and op[:2].isalpha():
            f["airline_iata"] = op[:2]
        result.append(f)
    return result


def _filter_terminal(flights: list, key: str, terminal: str) -> list:
    """Garde les vols dont le terminal (dep_terminal/arr_terminal) correspond.
    Correspondance souple : '2F'~'F'~'2 F' (inclusion dans un sens ou l'autre)."""
    t = _norm_terminal(terminal)
    if not t:
        return flights
    out = []
    for f in flights:
        val = _norm_terminal(f.get(key))
        if val and (t in val or val in t):
            out.append(f)
    return out


# --- tool functions ---

def get_airport_info(iata_code: str) -> dict:
    """Return key facts about an airport."""
    try:
        result = _fetch_airport(iata_code)
        if result is None:
            return {"error": f"Airport '{iata_code}' not found"}
        return _pick(result, _AIRPORT_KEYS)
    except AirlabsError as e:
        return {"error": str(e)}


def get_departures(iata_code: str, limit: int = 20, terminal: str = None,
                   destination: str = None, from_time: str = None) -> dict:
    """Return upcoming departures for an airport, optionally filtered by terminal,
    destination airport, and/or a start time. Pass 'destination' (IATA, e.g. 'JFK')
    for 'next flight to New York' — filtered by route server-side, so a flight late
    in the day is still found. Pass 'from_time' (e.g. '14:00') for 'flights from 2pm'."""
    try:
        cutoff = _parse_hour(from_time)
        if destination:
            flights = _fetch_schedules(dep_iata=iata_code, arr_iata=destination,
                                       limit=100, status="scheduled")
            if not flights:
                flights = _fetch_schedules(dep_iata=iata_code, arr_iata=destination, limit=100)
        else:
            flights = _fetch_board(dep_iata=iata_code)
            # Heure demandée hors de la fenêtre proche → reconstituer la journée
            # complète (fusion multi-compagnies) pour pouvoir la voir.
            if cutoff is not None and not _covers(flights, "dep_time", cutoff):
                flights = _fetch_day_board(dep_iata=iata_code)
        flights = _dedupe_codeshares(flights)
        if terminal:
            flights = _filter_terminal(flights, "dep_terminal", terminal)
        ordered = _order_by_time(flights, "dep_time", cutoff=cutoff, est_key="dep_estimated")
        shown   = ordered[: min(limit, 50)]
        out = {"count": len(shown), "terminal": terminal, "destination": destination,
               "from_time": from_time, "departures": [_summary_departure(f) for f in shown]}
        if from_time and not shown:
            # Heure demandée hors de la fenêtre visible (plafond API) : dire jusqu'où on voit.
            out["horizon"] = _max_time(flights, "dep_time")
        return out
    except AirlabsError as e:
        return {"error": str(e)}


def get_arrivals(iata_code: str, limit: int = 20, terminal: str = None,
                 origin: str = None, from_time: str = None) -> dict:
    """Return upcoming arrivals for an airport, optionally filtered by terminal,
    origin airport, and/or a start time. Pass 'origin' (IATA, e.g. 'JFK') for 'next
    flight from New York'. Pass 'from_time' (e.g. '14:00') for 'arrivals from 2pm'."""
    try:
        cutoff = _parse_hour(from_time)
        if origin:
            flights = _fetch_schedules(arr_iata=iata_code, dep_iata=origin,
                                       limit=100, status="scheduled")
            if not flights:
                flights = _fetch_schedules(arr_iata=iata_code, dep_iata=origin, limit=100)
        else:
            flights = _fetch_board(arr_iata=iata_code)
            if cutoff is not None and not _covers(flights, "arr_time", cutoff):
                flights = _fetch_day_board(arr_iata=iata_code)
        flights = _dedupe_codeshares(flights)
        if terminal:
            flights = _filter_terminal(flights, "arr_terminal", terminal)
        ordered = _order_by_time(flights, "arr_time", cutoff=cutoff, est_key="arr_estimated")
        shown   = ordered[: min(limit, 50)]
        out = {"count": len(shown), "terminal": terminal, "origin": origin,
               "from_time": from_time, "arrivals": [_summary_arrival(f) for f in shown]}
        if from_time and not shown:
            out["horizon"] = _max_time(flights, "arr_time")
        return out
    except AirlabsError as e:
        return {"error": str(e)}


def get_live_flights_for_airport(iata_code: str, direction: str = "departures") -> dict:
    """Return currently airborne flights for an airport."""
    try:
        if direction == "arrivals":
            flights = _fetch_live_flights(arr_iata=iata_code)
        else:
            flights = _fetch_live_flights(dep_iata=iata_code)
        trimmed = [_pick(f, _LIVE_KEYS) for f in flights[:30]]
        return {"count": len(flights), "shown": len(trimmed), "flights": trimmed}
    except AirlabsError as e:
        return {"error": str(e)}


def get_flight_status(flight_iata: str) -> dict:
    """Return the live status of a specific flight."""
    try:
        result = _fetch_flight(flight_iata)
        if result is None:
            return {"error": f"Flight '{flight_iata}' not found"}
        return _pick(result, _FLIGHT_KEYS)
    except AirlabsError as e:
        return {"error": str(e)}


def get_delayed_flights(iata_code: str, direction: str = "departures", min_delay: int = 30) -> dict:
    """Return delayed flights at an airport above a minimum delay threshold."""
    try:
        if direction == "arrivals":
            flights = _fetch_delays(arr_iata=iata_code, delay=max(30, min_delay), flight_type="arrivals")
        else:
            flights = _fetch_delays(dep_iata=iata_code, delay=max(30, min_delay), flight_type="departures")
        return {"count": len(flights), "delays": [_pick(f, _DELAY_KEYS) for f in flights]}
    except AirlabsError as e:
        return {"error": str(e)}


def get_airline_info(iata_code: str) -> dict:
    """Return information about an airline."""
    try:
        result = _fetch_airline(iata_code)
        if result is None:
            return {"error": f"Airline '{iata_code}' not found"}
        return _pick(result, _AIRLINE_KEYS)
    except AirlabsError as e:
        return {"error": str(e)}


# --- dispatch registry ---

TOOL_REGISTRY = {
    "get_airport_info": get_airport_info,
    "get_departures": get_departures,
    "get_arrivals": get_arrivals,
    "get_live_flights_for_airport": get_live_flights_for_airport,
    "get_flight_status": get_flight_status,
    "get_delayed_flights": get_delayed_flights,
    "get_airline_info": get_airline_info,
}


# --- OpenAI tool schemas ---

def _wrap(fn):
    def handler(**kwargs):
        return json.dumps(fn(**kwargs), ensure_ascii=False)
    return handler


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_airport_info",
            "description": (
                "Retrieve general information about an airport: name, city, country, "
                "coordinates, timezone, and runways. "
                "Use when the user asks about an airport itself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "iata_code": {
                        "type": "string",
                        "description": "The IATA airport code, e.g. 'CDG', 'LHR', 'JFK'.",
                    }
                },
                "required": ["iata_code"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_departures",
            "description": (
                "Get the scheduled departure board for an airport: flight numbers, "
                "airlines, destinations, departure times, terminals, gates, and status. "
                "Use when the user asks 'what flights depart from X' or 'show me the departure board'. "
                "Pass 'terminal' to only return departures from a specific terminal (e.g. '2F')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "iata_code": {
                        "type": "string",
                        "description": "IATA code of the departure airport.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of flights to return (default 20, max 50).",
                    },
                    "terminal": {
                        "type": "string",
                        "description": "Optional terminal filter, e.g. '2F', '2E', '1'. Omit for all terminals.",
                    },
                    "destination": {
                        "type": "string",
                        "description": "Optional destination airport IATA code (e.g. 'JFK', 'NRT'). Use for 'next flight to <city>' — returns the whole day's flights on that route, sorted by time.",
                    },
                    "from_time": {
                        "type": "string",
                        "description": "Optional start time 'HH:MM' (e.g. '14:00'). Only returns flights departing at or after this time today.",
                    },
                },
                "required": ["iata_code"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_arrivals",
            "description": (
                "Get the scheduled arrivals board for an airport: flight numbers, "
                "airlines, origin airports, arrival times, terminals, and status. "
                "Use when the user asks 'what flights arrive at X' or 'show me the arrivals board'. "
                "Pass 'terminal' to only return arrivals at a specific terminal (e.g. '2F')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "iata_code": {
                        "type": "string",
                        "description": "IATA code of the arrival airport.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of flights to return (default 20, max 50).",
                    },
                    "terminal": {
                        "type": "string",
                        "description": "Optional terminal filter, e.g. '2F', '2E', '1'. Omit for all terminals.",
                    },
                    "origin": {
                        "type": "string",
                        "description": "Optional origin airport IATA code (e.g. 'JFK'). Use for 'next flight from <city>' — returns the whole day's flights on that route, sorted by time.",
                    },
                    "from_time": {
                        "type": "string",
                        "description": "Optional start time 'HH:MM' (e.g. '14:00'). Only returns flights arriving at or after this time today.",
                    },
                },
                "required": ["iata_code"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_live_flights_for_airport",
            "description": (
                "Get real-time positions of flights currently in the air that departed from "
                "or are heading to an airport. Use when the user asks about planes currently "
                "in the air, live traffic, or airborne flights."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "iata_code": {
                        "type": "string",
                        "description": "IATA code of the airport.",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["departures", "arrivals"],
                        "description": (
                            "'departures' for flights that took off from this airport, "
                            "'arrivals' for flights heading to it."
                        ),
                    },
                },
                "required": ["iata_code"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_flight_status",
            "description": (
                "Get the current or most recent status of a specific flight by its IATA "
                "flight code (e.g. 'AF1234', 'LH456'). Returns position, times, delays, "
                "gate, terminal, and aircraft info. Use when the user mentions a flight number."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "flight_iata": {
                        "type": "string",
                        "description": "The IATA flight code, e.g. 'AF1234' or 'BA303'.",
                    }
                },
                "required": ["flight_iata"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_delayed_flights",
            "description": (
                "Get flights delayed beyond a minimum threshold at an airport. "
                "Use when the user asks about delays, disruptions, or late flights."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "iata_code": {
                        "type": "string",
                        "description": "IATA code of the airport to check for delays.",
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["departures", "arrivals"],
                        "description": "Whether to check departing or arriving flights. Default: 'departures'.",
                    },
                    "min_delay": {
                        "type": "integer",
                        "description": "Minimum delay in minutes (minimum 30, default 30).",
                    },
                },
                "required": ["iata_code"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_airline_info",
            "description": (
                "Retrieve information about an airline by its IATA code: full name, "
                "country, fleet size, and service type. Use when the user asks about an airline."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "iata_code": {
                        "type": "string",
                        "description": "The IATA airline code, e.g. 'AF' for Air France, 'LH' for Lufthansa.",
                    }
                },
                "required": ["iata_code"],
                "additionalProperties": False,
            },
        },
    },
]


# --- register into project registry ---

from tools.registry import register  # noqa: E402

for _tool in TOOLS:
    _schema = _tool["function"]
    register(_schema, _wrap(TOOL_REGISTRY[_schema["name"]]))
