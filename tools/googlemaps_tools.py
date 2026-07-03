"""Google Maps API tools — HTTP client, tool functions, and OpenAI schemas in one place."""

import os
from typing import Callable, List, Optional
import httpx

# Robot static position — Terminal 2F, CDG Roissy. Used as the default centre
# for every location-biased tool (search, route origin…).
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
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params)
    except httpx.HTTPError as e:
        raise GoogleMapsError(f"network error: {e}")
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
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as e:
        raise GoogleMapsError(f"network error: {e}")
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

        field_mask = "places.id,places.displayName,places.types,places.formattedAddress,places.location,places.rating,places.currentOpeningHours.openNow,places.accessibilityOptions"
        data = _post(f"{_PLACES_BASE}/places:searchNearby", payload, field_mask)
        return {"places": data.get("places", [])}
    except GoogleMapsError as e:
        return {"error": str(e)}


def search_places_text(
    query: str,
    lat: float = ROBOT_LAT,
    lng: float = ROBOT_LNG,
    radius_m: float = 2000.0,
    max_results: int = 10,
) -> dict:
    """Search for places by free-text query, biased toward the given location (defaults to CDG)."""
    try:
        payload: dict = {
            "textQuery": query,
            "maxResultCount": min(max(1, max_results), 20),
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": min(radius_m, 50000.0),
                }
            },
        }
        field_mask = "places.id,places.displayName,places.types,places.formattedAddress,places.location,places.rating,places.currentOpeningHours.openNow,places.websiteUri,places.accessibilityOptions"
        data = _post(f"{_PLACES_BASE}/places:searchText", payload, field_mask)
        return {"places": data.get("places", [])}
    except GoogleMapsError as e:
        return {"error": str(e)}


def get_place_details(place_id: str) -> dict:
    """Retrieve full details about a place: hours, accessibility, phone, website,
    rating and up to 5 user reviews (author, score, text)."""
    try:
        field_mask = (
            "id,displayName,formattedAddress,location,types,"
            "regularOpeningHours,currentOpeningHours,websiteUri,"
            "internationalPhoneNumber,accessibilityOptions,priceLevel,"
            "editorialSummary,rating,userRatingCount,reviews"
        )
        headers = {
            "X-Goog-Api-Key": _api_key(),
            "X-Goog-FieldMask": field_mask,
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{_PLACES_BASE}/places/{place_id}", headers=headers)
        except httpx.HTTPError as e:
            raise GoogleMapsError(f"network error: {e}")
        if not response.is_success:
            raise GoogleMapsError(f"HTTP {response.status_code}: {response.text[:200]}")
        data = response.json()
        # Trim the verbose reviews payload to what a voice answer needs.
        if "reviews" in data:
            data["reviews"] = [
                {
                    "author": r.get("authorAttribution", {}).get("displayName"),
                    "rating": r.get("rating"),
                    "when": r.get("relativePublishTimeDescription"),
                    "text": (r.get("text") or r.get("originalText") or {}).get("text"),
                }
                for r in data["reviews"]
            ]
        if isinstance(data.get("editorialSummary"), dict):
            data["editorialSummary"] = data["editorialSummary"].get("text")
        return data
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
    departure_time: Optional[str] = None,
) -> dict:
    """Calculate the route and turn-by-turn steps between two coordinates.

    For TRANSIT mode the response also carries line names, stops, schedules and fare.
    `departure_time`: optional RFC3339 timestamp (e.g. '2026-06-19T14:00:00Z').
    """
    mode = travel_mode.upper()
    try:
        payload: dict = {
            "origin": {"location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}},
            "destination": {"location": {"latLng": {"latitude": dest_lat, "longitude": dest_lng}}},
            "travelMode": mode,
            "computeAlternativeRoutes": False,
        }
        if departure_time:
            payload["departureTime"] = departure_time
        if mode == "DRIVE":
            # Traffic-aware ETA — only valid for DRIVE/TWO_WHEELER.
            payload["routingPreference"] = "TRAFFIC_AWARE"

        field_mask = (
            "routes.distanceMeters,routes.duration,"
            "routes.legs.steps.navigationInstruction,"
            "routes.legs.distanceMeters,routes.legs.duration"
        )
        if mode == "TRANSIT":
            # Transit legs expose line/stop/schedule under transitDetails + a fare.
            field_mask += (
                ",routes.legs.steps.transitDetails,"
                "routes.travelAdvisory.transitFare,routes.localizedValues"
            )
        data = _post(f"{_ROUTES_BASE}:computeRoutes", payload, field_mask)
        routes = data.get("routes", [])
        if not routes:
            return {"error": "No route found between the given points"}
        route = routes[0]
        result = {
            "distance_meters": route.get("distanceMeters"),
            "duration": route.get("duration"),
            "legs": route.get("legs", []),
        }
        if mode == "TRANSIT":
            advisory = route.get("travelAdvisory", {})
            if advisory.get("transitFare"):
                result["fare"] = advisory["transitFare"]
        return result
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


def place_autocomplete(
    input: str,
    lat: float = ROBOT_LAT,
    lng: float = ROBOT_LNG,
    radius_m: float = 5000.0,
) -> dict:
    """Resolve a partial / spoken place name into ranked predictions (place name + place_id).

    Useful before geocode/route when the user gives an incomplete or fuzzy name.
    """
    try:
        payload: dict = {
            "input": input,
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": min(radius_m, 50000.0),
                }
            },
            "languageCode": "fr",
        }
        # Autocomplete (New) ignores X-Goog-FieldMask; everything is returned.
        data = _post(f"{_PLACES_BASE}/places:autocomplete", payload, "*")
        predictions = []
        for s in data.get("suggestions", []):
            pp = s.get("placePrediction")
            if not pp:
                continue
            predictions.append({
                "place_id": pp.get("placeId"),
                "text": pp.get("text", {}).get("text"),
                "types": pp.get("types", []),
            })
        return {"predictions": predictions}
    except GoogleMapsError as e:
        return {"error": str(e)}


# --- dispatch registry ---

TOOL_REGISTRY = {
    "search_nearby_places": search_nearby_places,
    "search_places_text": search_places_text,
    "get_place_details": get_place_details,
    "place_autocomplete": place_autocomplete,
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
                "Each result includes wheelchair accessibility info (entrance/parking/restroom/seating) when known. "
                "If no coordinates are given, the robot's position (Terminal 2F CDG) is used."
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
                    "lat": {"type": "number", "description": "Latitude to bias results toward (default: robot position, Terminal 2F CDG)."},
                    "lng": {"type": "number", "description": "Longitude to bias results toward (default: robot position, Terminal 2F CDG)."},
                    "radius_m": {"type": "number", "description": "Bias radius in metres (default 2000)."},
                    "max_results": {"type": "integer", "description": "Max number of places to return (1-20, default 10)."},
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
                "opening hours, phone number, website, accessibility, price level, editorial summary, "
                "overall rating AND up to 5 user reviews (author, score, text). "
                "Use after search_nearby_places/search_places_text/place_autocomplete to read "
                "the notes and reviews of a place."
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
            "name": "place_autocomplete",
            "description": (
                "Turn a partial, fuzzy or spoken place name into a short list of ranked "
                "predictions (each with a name and a Google Place ID). Use FIRST when the user "
                "names a place imprecisely ('le hall des départs', 'la gare RER'), then feed the "
                "chosen place_id to get_place_details, or its name to geocode_address before routing. "
                "Results are biased near CDG by default."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "Partial text typed/spoken by the user."},
                    "lat": {"type": "number", "description": "Latitude to bias predictions toward (default CDG)."},
                    "lng": {"type": "number", "description": "Longitude to bias predictions toward (default CDG)."},
                    "radius_m": {"type": "number", "description": "Bias radius in metres (default 5000, max 50000)."},
                },
                "required": ["input"],
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
                    "departure_time": {
                        "type": "string",
                        "description": (
                            "Optional RFC3339 departure time, e.g. '2026-06-19T14:00:00Z'. "
                            "Use for TRANSIT (next departures) or DRIVE (traffic-aware ETA)."
                        ),
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
