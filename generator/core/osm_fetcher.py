"""OpenStreetMap data fetching via Overpass API."""
from __future__ import annotations

from dataclasses import dataclass, field

import requests

from .location import TrackArea

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 60


@dataclass
class OSMNode:
    id: int
    lat: float
    lon: float
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class OSMWay:
    id: int
    node_ids: list[int]
    tags: dict[str, str] = field(default_factory=dict)
    nodes: list[OSMNode] = field(default_factory=list)


@dataclass
class OSMData:
    roads: list[OSMWay] = field(default_factory=list)
    forests: list[OSMWay] = field(default_factory=list)
    trees: list[OSMNode] = field(default_factory=list)
    buildings: list[OSMWay] = field(default_factory=list)
    traffic_signs: list[OSMNode] = field(default_factory=list)
    all_nodes: dict[int, OSMNode] = field(default_factory=dict)


# Road type to width in meters
ROAD_WIDTHS: dict[str, float] = {
    "motorway": 14.0,
    "motorway_link": 8.0,
    "trunk": 12.0,
    "trunk_link": 7.0,
    "primary": 9.0,
    "primary_link": 6.0,
    "secondary": 7.5,
    "secondary_link": 5.0,
    "tertiary": 6.0,
    "tertiary_link": 4.5,
    "residential": 5.0,
    "unclassified": 5.0,
    "service": 4.0,
    "track": 3.5,
    "living_street": 4.5,
}

# Road type to speed limit (km/h, for banking calculation)
ROAD_SPEEDS: dict[str, float] = {
    "motorway": 130.0,
    "motorway_link": 80.0,
    "trunk": 100.0,
    "trunk_link": 70.0,
    "primary": 80.0,
    "primary_link": 60.0,
    "secondary": 60.0,
    "secondary_link": 50.0,
    "tertiary": 50.0,
    "tertiary_link": 40.0,
    "residential": 30.0,
    "unclassified": 40.0,
    "service": 20.0,
    "track": 30.0,
    "living_street": 20.0,
}


def fetch_osm_data(area: TrackArea, progress_cb=None) -> OSMData:
    """
    Fetch all relevant OSM data for the given area.

    Args:
        area: The geographic bounding box to query
        progress_cb: Optional callback(message: str) for progress updates

    Returns:
        OSMData with roads, trees, forests, buildings, signs
    """
    bbox = f"{area.min_lat},{area.min_lon},{area.max_lat},{area.max_lon}"

    if progress_cb:
        progress_cb("Fetching OpenStreetMap data...")

    query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT}];
(
  way["highway"]["highway"!~"footway|cycleway|steps|path|pedestrian|corridor"](bbox:{bbox});
  way["landuse"="forest"](bbox:{bbox});
  way["natural"="wood"](bbox:{bbox});
  way["building"](bbox:{bbox});
  node["natural"="tree"](bbox:{bbox});
  node["traffic_sign"](bbox:{bbox});
  node["highway"="traffic_signals"](bbox:{bbox});
  node["highway"="stop"](bbox:{bbox});
  node["highway"="give_way"](bbox:{bbox});
);
out body;
>;
out skel qt;
"""

    try:
        response = requests.post(
            OVERPASS_URL,
            data={"data": query},
            timeout=OVERPASS_TIMEOUT + 10,
            headers={"User-Agent": "AC-Track-Generator/1.0"},
        )
        response.raise_for_status()
        raw = response.json()
    except Exception as e:
        raise RuntimeError(f"OSM data fetch failed: {e}") from e

    return _parse_osm_response(raw)


def _parse_osm_response(raw: dict) -> OSMData:
    """Parse Overpass API JSON response into structured OSMData."""
    data = OSMData()
    node_map: dict[int, OSMNode] = {}

    # First pass: collect all nodes
    for element in raw.get("elements", []):
        if element["type"] == "node":
            node = OSMNode(
                id=element["id"],
                lat=element["lat"],
                lon=element["lon"],
                tags=element.get("tags", {}),
            )
            node_map[node.id] = node

    data.all_nodes = node_map

    # Second pass: collect ways and assign nodes
    for element in raw.get("elements", []):
        if element["type"] != "way":
            continue

        tags = element.get("tags", {})
        node_ids = element.get("nodes", [])
        nodes = [node_map[nid] for nid in node_ids if nid in node_map]

        way = OSMWay(id=element["id"], node_ids=node_ids, tags=tags, nodes=nodes)

        if "highway" in tags and tags["highway"] in ROAD_WIDTHS:
            data.roads.append(way)
        elif tags.get("landuse") in ("forest",) or tags.get("natural") in ("wood",):
            data.forests.append(way)
        elif "building" in tags:
            data.buildings.append(way)

    # Categorize nodes
    for node in node_map.values():
        tags = node.tags
        if tags.get("natural") == "tree":
            data.trees.append(node)
        elif (
            "traffic_sign" in tags
            or tags.get("highway") in ("traffic_signals", "stop", "give_way")
        ):
            data.traffic_signs.append(node)

    return data


def get_road_width(way: OSMWay) -> float:
    """Get road width in meters, checking OSM width tag first."""
    # Check explicit width tag
    if "width" in way.tags:
        try:
            return float(way.tags["width"])
        except ValueError:
            pass
    highway_type = way.tags.get("highway", "residential")
    return ROAD_WIDTHS.get(highway_type, 5.0)


def get_road_speed(way: OSMWay) -> float:
    """Get road speed limit in km/h."""
    if "maxspeed" in way.tags:
        speed_str = way.tags["maxspeed"].replace("mph", "").replace("km/h", "").strip()
        try:
            speed = float(speed_str)
            if "mph" in way.tags.get("maxspeed", ""):
                speed *= 1.60934
            return speed
        except ValueError:
            pass
    highway_type = way.tags.get("highway", "residential")
    return ROAD_SPEEDS.get(highway_type, 50.0)
