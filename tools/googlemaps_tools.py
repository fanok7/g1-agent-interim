"""Google Maps API tools — HTTP client, tool functions, and OpenAI schemas in one place."""

import os
from typing import Callable, List, Optional
import httpx

# Robot static position — Terminal 2F, CDG Roissy
ROBOT_LAT = 49.0052
ROBOT_LNG = 2.5770

_PLACES_BASE = "https://places.googleapis.com/v1"
_GEOCODING_BASE = "https://maps.googleapis.com/maps/api/geocode/json"
_ROUTES_BASE = "https://routes.googleapis.com/directions/v2"


class GoogleMapsError(Exception):
    pass


def _api_key() -> str:
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not set")
    return key


def _get(url: str, params: dict) -> dict:
    with httpx.Client(timeout=10.0) as client:
        response = client.get(url, params=params)
    if not response.is_success:
        raise GoogleMapsError(f"HTTP {response.status_code}: {response.text[:200]}")
    data = response.json()
    if "error_message" in data:
        raise GoogleMapsError(data["error_message"])
    return data


def _post(url: str, payload: dict, field_mask: str) -> dict:
    headers = {
        "X-Goog-Api-Key": _api_key(),
        "X-Goog-FieldMask": field_mask,
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=10.0) as client:
        response = client.post(url, json=payload, headers=headers)
    if not response.is_success:
        raise GoogleMapsError(f"HTTP {response.status_code}: {response.text[:200]}")
    return response.json()


# --- tool functions ---

def search_nearby_places(
    lat: float = ROBOT_LAT,
    lng: float = ROBOT_LNG,
    radius_m: float = 500.0,
    place_types: Optional[List[str]] = None,
    max_results: int = 10,
) -> dict:
    """Find places near a coordinate within a radius. Good for locating amenities around the robot."""
    try:
        payload: dict = {
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": min(radius_m, 50000.0),
                }
            },
            "maxResultCount": min(max(1, max_results), 20),
            "rankPreference": "DISTANCE",
        }
        if place_types:
            payload["includedTypes"] = place_types

        field_mask = "places.id,places.displayName,places.types,places.formattedAddress,places.location,places.rating,places.currentOpeningHours.openNow"
        data = _post(f"{_PLACES_BASE}/places:searchNearby", payload, field_mask)
        return {"places": data.get("places", [])}
    except GoogleMapsError as e:
        return {"error": str(e)}


def search_places_text(
    query: str,
    lat: float = ROBOT_LAT,
    lng: float = ROBOT_LNG,
    radius_m: float = 2000.0,
) -> dict:
    """Search for places by free-text query, biased toward the given location (defaults to CDG)."""
    try:
        payload: dict = {
            "textQuery": query,
            "maxResultCount": 10,
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": min(radius_m, 50000.0),
                }
            },
        }
        field_mask = "places.id,places.displayName,places.types,places.formattedAddress,places.location,places.rating,places.currentOpeningHours.openNow,places.websiteUri"
        data = _post(f"{_PLACES_BASE}/places:searchText", payload, field_mask)
        return {"places": data.get("places", [])}
    except GoogleMapsError as e:
        return {"error": str(e)}


def get_place_details(place_id: str) -> dict:
    """Retrieve full details about a place: hours, accessibility, phone, website, reviews."""
    try:
        field_mask = (
            "id,displayName,formattedAddress,location,types,"
            "regularOpeningHours,currentOpeningHours,websiteUri,"
            "internationalPhoneNumber,accessibilityOptions,"
            "rating,userRatingCount"
        )
        headers = {
            "X-Goog-Api-Key": _api_key(),
            "X-Goog-FieldMask": field_mask,
        }
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{_PLACES_BASE}/places/{place_id}", headers=headers)
        if not response.is_success:
            raise GoogleMapsError(f"HTTP {response.status_code}: {response.text[:200]}")
        return response.json()
    except GoogleMapsError as e:
        return {"error": str(e)}


def geocode_address(address: str) -> dict:
    """Convert a human-readable address or landmark name to GPS coordinates."""
    try:
        data = _get(_GEOCODING_BASE, {"address": address, "key": _api_key()})
        results = data.get("results", [])
        if not results:
            return {"error": f"No geocoding results for: {address}"}
        top = results[0]
        return {
            "formatted_address": top.get("formatted_address"),
            "location": top["geometry"]["location"],
            "place_id": top.get("place_id"),
            "types": top.get("types", []),
        }
    except GoogleMapsError as e:
        return {"error": str(e)}


def reverse_geocode(lat: float, lng: float) -> dict:
    """Convert GPS coordinates to the nearest human-readable address."""
    try:
        data = _get(_GEOCODING_BASE, {"latlng": f"{lat},{lng}", "key": _api_key()})
        results = data.get("results", [])
        if not results:
            return {"error": f"No results for coordinates ({lat}, {lng})"}
        top = results[0]
        return {
            "formatted_address": top.get("formatted_address"),
            "place_id": top.get("place_id"),
            "types": top.get("types", []),
            "address_components": top.get("address_components", []),
        }
    except GoogleMapsError as e:
        return {"error": str(e)}


def compute_route(
    origin_lat: float = ROBOT_LAT,
    origin_lng: float = ROBOT_LNG,
    dest_lat: float = ROBOT_LAT,
    dest_lng: float = ROBOT_LNG,
    travel_mode: str = "WALK",
) -> dict:
    """Calculate the route and turn-by-turn steps between two coordinates."""
    try:
        payload = {
            "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}},
            "destination": {"location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}},
            "travelMode": travel_mode.upper(),
            "computeAlternativeRoutes": False,
        }
        field_mask = "routes.distanceMeters,routes.duration,routes.legs.steps.navigationInstruction,routes.legs.distanceMeters,routes.legs.duration"
        data = _post(f"{_ROUTES_BASE}:computeRoutes", payload, field_mask)
        routes = data.get("routes", [])
        if not routes:
            return {"error": "No route found between the given points"}
        route = routes[0]
        return {
            "distance_meters": route.get("distanceMeters"),
            "duration": route.get("duration"),
            "legs": route.get("legs", []),
        }
    except GoogleMapsError as e:
        return {"error": str(e)}


def compute_route_matrix(
    origins: List[dict],
    destinations: List[dict],
    travel_mode: str = "WALK",
) -> dict:
    """Compute travel distances/durations from multiple origins to multiple destinations.

    origins / destinations: list of {"lat": float, "lng": float} dicts.
    """
    _MODE_MAP = {"WALK": "walking", "DRIVE": "driving", "TRANSIT": "transit", "BICYCLE": "bicycling"}
    try:
        origins_str = "|".join(f"{o['lat']},{o['lng']}" for o in origins)
        destinations_str = "|".join(f"{d['lat']},{d['lng']}" for d in destinations)
        mode = _MODE_MAP.get(travel_mode.upper(), "walking")
        data = _get(
            "https://maps.googleapis.com/maps/api/distancematrix/json",
            {"origins": origins_str, "destinations": destinations_str, "mode": mode, "key": _api_key()},
        )
        rows = data.get("rows", [])
        dest_addresses = data.get("destination_addresses", [])
        matrix = []
        for o_idx, row in enumerate(rows):
            for d_idx, element in enumerate(row.get("elements", [])):
                matrix.append({
                    "origin_index": o_idx,
                    "destination_index": d_idx,
                    "destination_address": dest_addresses[d_idx] if d_idx < len(dest_addresses) else None,
                    "distance": element.get("distance"),
                    "duration": element.get("duration"),
                    "status": element.get("status"),
                })
        return {"matrix": matrix}
    except GoogleMapsError as e:
        return {"error": str(e)}


# --- dispatch registry ---

TOOL_REGISTRY = {
    "search_nearby_places": search_nearby_places,
    "search_places_text": search_places_text,
    "get_place_details": get_place_details,
    "geocode_address": geocode_address,
    "reverse_geocode": reverse_geocode,
    "compute_route": compute_route,
    "compute_route_matrix": compute_route_matrix,
}


# --- OpenAI tool schemas ---

from tools.registry import register as _register  # noqa: E402

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_nearby_places",
            "description": (
                "Find places within a radius of a GPS coordinate. "
                "Use to locate nearby amenities: restrooms, gates, shops, ATMs, lounges, "
                "restaurants, information desks. Optionally filter by place type. "
                "If no coordinates are given, use CDG centre (49.0097, 2.5479)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Latitude of search centre."},
                    "lng": {"type": "number", "description": "Longitude of search centre."},
                    "radius_m": {"type": "number", "description": "Search radius in metres (default 500, max 50000)."},
                    "place_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                # services
                                "public_bathroom",
                                "atm", "bank",
                                "pharmacy", "hospital", "doctor", "dentist", "police",
                                "post_office", "laundry", "hair_salon", "spa", "beauty_salon",
                                # food & drink
                                "restaurant", "fast_food_restaurant", "cafe", "bar",
                                "bakery", "sandwich_shop", "food_court", "ice_cream_shop",
                                "pizza_restaurant", "seafood_restaurant",
                                "breakfast_restaurant", "brunch_restaurant",
                                # shopping
                                "store", "convenience_store", "shopping_mall",
                                "clothing_store", "shoe_store", "jewelry_store",
                                "book_store", "electronics_store", "gift_shop",
                                "drugstore", "supermarket", "grocery_store",
                                "department_store", "cosmetics_store", "sporting_goods_store",
                                # transport
                                "airport", "transit_station",
                                "bus_station", "bus_stop", "taxi_stand",
                                "train_station", "subway_station", "light_rail_station",
                                "car_rental", "parking", "gas_station",
                                # accommodation
                                "hotel", "lodging", "motel",
                                "extended_stay_hotel", "resort_hotel",
                                # misc
                                "tourist_attraction", "storage",
                            ],
                        },
                        "description": (
                            "Optional place type filters. Use ONLY values from the enum list. "
                            "'public_bathroom'=toilettes, 'atm'=distributeur, 'car_rental'=location voiture, "
                            "'taxi_stand'=taxis, 'bus_stop'=navettes, 'train_station'=RER/train. "
                            "Omit to return all types."
                        ),
                    },
                    "max_results": {"type": "integer", "description": "Max number of places to return (1-20, default 10)."},
                },
                "required": ["lat", "lng"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_places_text",
            "description": (
                "Search for a specific place by name or description near a location. "
                "Use when the user mentions a named facility: 'Air France lounge T2F', "
                "'baggage claim Terminal 1', 'CDG shuttle bus stop'. "
                "Defaults to searching near CDG airport if no coordinates given."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Free-text search query, e.g. 'Air France lounge Terminal 2F CDG'."},
                    "lat": {"type": "number", "description": "Latitude to bias results toward (default CDG 49.0097)."},
                    "lng": {"type": "number", "description": "Longitude to bias results toward (default CDG 2.5479)."},
                    "radius_m": {"type": "number", "description": "Bias radius in metres (default 2000)."},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_place_details",
            "description": (
                "Retrieve full details for a specific place by its Google Place ID: "
                "opening hours, phone number, website, accessibility options, and rating. "
                "Use after search_nearby_places or search_places_text to get more info about a result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "place_id": {
                        "type": "string",
                        "description": "Google Place ID, e.g. 'places/ChIJ...' or just the ID string.",
                    }
                },
                "required": ["place_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "geocode_address",
            "description": (
                "Convert a human-readable address or landmark name to GPS coordinates. "
                "Use to resolve terminal names, gate addresses, or points of interest to lat/lng "
                "before routing. E.g. 'Terminal 2E CDG', 'Hall M Paris CDG'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Address or place name to geocode, e.g. 'Terminal 2F Charles de Gaulle Airport'.",
                    }
                },
                "required": ["address"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reverse_geocode",
            "description": (
                "Convert GPS coordinates to the nearest human-readable address. "
                "Use to translate the robot's current position into a readable location name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "Latitude of the position to reverse-geocode."},
                    "lng": {"type": "number", "description": "Longitude of the position to reverse-geocode."},
                },
                "required": ["lat", "lng"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_route",
            "description": (
                "Calculate a route between two GPS coordinates, including distance, duration, "
                "and turn-by-turn navigation steps. Default travel mode is WALK (indoor). "
                "Use to guide the robot or a passenger from one location to another."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origin_lat": {"type": "number", "description": "Latitude of the starting point."},
                    "origin_lng": {"type": "number", "description": "Longitude of the starting point."},
                    "dest_lat": {"type": "number", "description": "Latitude of the destination."},
                    "dest_lng": {"type": "number", "description": "Longitude of the destination."},
                    "travel_mode": {
                        "type": "string",
                        "enum": ["WALK", "DRIVE", "TRANSIT", "BICYCLE"],
                        "description": "Travel mode (default WALK for indoor airport navigation).",
                    },
                },
                "required": ["origin_lat", "origin_lng", "dest_lat", "dest_lng"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_route_matrix",
            "description": (
                "Compute travel distances and durations from one or more origins to one or more "
                "destinations in a single batch call. Use to find the closest facility among several "
                "options from the robot's current position."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "origins": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "lat": {"type": "number"},
                                "lng": {"type": "number"},
                            },
                            "required": ["lat", "lng"],
                        },
                        "description": "List of origin coordinates, e.g. [{'lat': 49.01, 'lng': 2.55}].",
                    },
                    "destinations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "lat": {"type": "number"},
                                "lng": {"type": "number"},
                            },
                            "required": ["lat", "lng"],
                        },
                        "description": "List of destination coordinates.",
                    },
                    "travel_mode": {
                        "type": "string",
                        "enum": ["WALK", "DRIVE", "TRANSIT", "BICYCLE"],
                        "description": "Travel mode (default WALK).",
                    },
                },
                "required": ["origins", "destinations"],
                "additionalProperties": False,
            },
        },
    },
]


# --- register into project registry ---

import json as _json  # noqa: E402


def _wrap(fn):
    def handler(**kwargs):
        return _json.dumps(fn(**kwargs), ensure_ascii=False)
    return handler


for _tool in TOOLS:
    _schema = _tool["function"]
    _register(_schema, _wrap(TOOL_REGISTRY[_schema["name"]]))
