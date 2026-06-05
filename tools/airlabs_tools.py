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
    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{_BASE_URL}{path}", params=params)
    if not response.is_success:
        raise AirlabsError(f"HTTP {response.status_code}: {response.text[:200]}")
    data = response.json()
    if "error" in data:
        raise AirlabsError(data["error"].get("message", str(data["error"])))
    return data


def _fetch_airport(iata_code: str) -> Optional[dict]:
    data = _get("/airports", {"iata_code": iata_code})
    results = data.get("response", [])
    return results[0] if results else None


def _fetch_schedules(*, dep_iata: Optional[str] = None, arr_iata: Optional[str] = None, limit: int = 50) -> list:
    params: dict = {"limit": limit}
    if dep_iata:
        params["dep_iata"] = dep_iata
    if arr_iata:
        params["arr_iata"] = arr_iata
    return _get("/schedules", params).get("response", [])


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


def get_departures(iata_code: str, limit: int = 20) -> dict:
    """Return the scheduled departure board for an airport."""
    try:
        flights = _fetch_schedules(dep_iata=iata_code, limit=min(limit, 50))
        return {"count": len(flights), "departures": [_pick(f, _SCHEDULE_KEYS) for f in flights]}
    except AirlabsError as e:
        return {"error": str(e)}


def get_arrivals(iata_code: str, limit: int = 20) -> dict:
    """Return the scheduled arrivals board for an airport."""
    try:
        flights = _fetch_schedules(arr_iata=iata_code, limit=min(limit, 50))
        return {"count": len(flights), "arrivals": [_pick(f, _SCHEDULE_KEYS) for f in flights]}
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
                "Use when the user asks 'what flights depart from X' or 'show me the departure board'."
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
                "Use when the user asks 'what flights arrive at X' or 'show me the arrivals board'."
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
