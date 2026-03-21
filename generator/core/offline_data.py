"""
Offline/synthetic OSM data for use when external APIs are unavailable.

Contains hardcoded route data for well-known tracks and a synthetic
road generator for use with coordinates when live API access is blocked.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .osm_fetcher import OSMData, OSMNode, OSMWay, ROAD_WIDTHS


# Hardcoded routes: (name_key, list of (lat, lon) waypoints, highway_type, name_tag)
KNOWN_ROUTES: dict[str, dict] = {
    "palisades_parkway": {
        "name": "Palisades Interstate Parkway",
        "highway": "motorway",
        "waypoints": [
            # ── South terminus: Fort Lee / Route 9W interchange, NJ ─────────
            (40.8474, -73.9637),
            (40.8530, -73.9662),
            (40.8590, -73.9685),
            (40.8650, -73.9706),
            # Englewood Cliffs
            (40.8720, -73.9728),
            (40.8790, -73.9748),
            (40.8860, -73.9766),
            (40.8930, -73.9782),
            # Alpine, NJ — exit 2
            (40.9010, -73.9797),
            (40.9090, -73.9810),
            (40.9170, -73.9822),
            # State Line Lookout area (NJ/NY border)
            (40.9260, -73.9835),
            (40.9350, -73.9846),
            (40.9440, -73.9856),
            (40.9530, -73.9864),
            (40.9620, -73.9872),
            (40.9720, -73.9879),
            (40.9820, -73.9884),
            # Crosses NY state line
            (40.9920, -73.9889),
            (41.0020, -73.9893),
            (41.0120, -73.9897),
            (41.0230, -73.9900),
            (41.0340, -73.9903),
            (41.0450, -73.9907),
            # Rockland County, NY — exits 4–9
            (41.0560, -73.9910),
            (41.0670, -73.9914),
            (41.0780, -73.9918),
            (41.0900, -73.9921),
            (41.1020, -73.9922),
            (41.1140, -73.9921),
            # Harriman State Park begins
            (41.1260, -73.9918),
            (41.1380, -73.9914),
            (41.1500, -73.9908),
            (41.1620, -73.9900),
            # Tiorati Brook Road interchange
            (41.1740, -73.9889),
            (41.1860, -73.9875),
            (41.1980, -73.9858),
            (41.2100, -73.9838),
            # Anthony Wayne Recreation Area
            (41.2220, -73.9815),
            (41.2340, -73.9789),
            (41.2460, -73.9760),
            (41.2580, -73.9728),
            # Approaching Bear Mountain
            (41.2700, -73.9693),
            (41.2820, -73.9655),
            (41.2940, -73.9614),
            (41.3060, -73.9570),
            # ── North terminus: Bear Mountain / Route 6 & 202 circle ────────
            (41.3148, -73.9528),
        ],
    },
    "nurburgring": {
        "name": "Nurburgring Nordschleife (approx)",
        "highway": "track",
        "waypoints": [
            (50.3356, 6.9475),
            (50.3420, 6.9550),
            (50.3500, 6.9610),
            (50.3580, 6.9700),
            (50.3620, 6.9810),
            (50.3680, 6.9890),
            (50.3720, 6.9960),
            (50.3750, 7.0050),
            (50.3700, 7.0130),
            (50.3640, 7.0200),
            (50.3560, 7.0270),
            (50.3480, 7.0300),
            (50.3400, 7.0280),
            (50.3340, 7.0230),
            (50.3290, 7.0150),
            (50.3260, 7.0060),
            (50.3280, 6.9970),
            (50.3310, 6.9880),
            (50.3340, 6.9780),
            (50.3356, 6.9475),  # Close the loop
        ],
    },
}


def make_synthetic_osm(
    area,
    route_key: str | None = None,
    road_type: str = "primary",
) -> OSMData:
    """
    Build synthetic OSMData for a given area.

    If route_key matches a known route, use its waypoints.
    Otherwise generate a simple oval road shape spanning the area.
    """
    data = OSMData()
    node_id = 1000000

    # Check if we have a matching known route
    route = None
    if route_key:
        for key, r in KNOWN_ROUTES.items():
            if key in route_key.lower() or route_key.lower() in key:
                route = r
                break

    if route is None:
        # Search by location name
        location_lower = area.name.lower()
        for key, r in KNOWN_ROUTES.items():
            if any(word in location_lower for word in key.split("_")):
                route = r
                break

    if route:
        nodes = _make_nodes_from_waypoints(route["waypoints"], node_id)
        road_name = route["name"]
        highway_type = route.get("highway", road_type)
    else:
        # Generate a simple oval shape
        nodes = _make_oval_nodes(area, node_id)
        road_name = area.name
        highway_type = road_type

    for node in nodes:
        data.all_nodes[node.id] = node

    way = OSMWay(
        id=node_id - 1,
        node_ids=[n.id for n in nodes],
        tags={
            "highway": highway_type,
            "name": road_name,
            "maxspeed": "90",
        },
        nodes=nodes,
    )
    data.roads.append(way)

    # Add some synthetic trees around the road
    data.trees = _scatter_trees(area, nodes, node_id + len(nodes))

    return data


def _make_nodes_from_waypoints(
    waypoints: list[tuple[float, float]], start_id: int
) -> list[OSMNode]:
    """Convert (lat, lon) waypoints to OSMNode objects."""
    nodes = []
    for i, (lat, lon) in enumerate(waypoints):
        nodes.append(OSMNode(id=start_id + i, lat=lat, lon=lon))
    return nodes


def _make_oval_nodes(area, start_id: int, segments: int = 36) -> list[OSMNode]:
    """Generate an oval road around the area center."""
    nodes = []
    center_lat = area.center_lat
    center_lon = area.center_lon

    # Oval dimensions: 60% of area radius
    radius_km = area.radius_km * 0.6
    delta_lat = radius_km / 111.32
    delta_lon = radius_km / (111.32 * math.cos(math.radians(center_lat)))

    for i in range(segments + 1):
        angle = (2 * math.pi * i) / segments
        lat = center_lat + delta_lat * math.sin(angle)
        lon = center_lon + delta_lon * math.cos(angle)
        nodes.append(OSMNode(id=start_id + i, lat=lat, lon=lon))

    return nodes


def _scatter_trees(
    area, road_nodes: list[OSMNode], start_id: int
) -> list[OSMNode]:
    """Scatter some tree nodes along the road sides."""
    import random
    rng = random.Random(42)
    trees = []
    tree_id = start_id

    for i, node in enumerate(road_nodes[:-1]):
        if rng.random() > 0.3:  # 30% chance of tree per road segment
            continue

        # Place tree offset from road
        offset_lat = rng.uniform(-0.001, 0.001)
        offset_lon = rng.uniform(-0.001, 0.001)
        tree = OSMNode(
            id=tree_id,
            lat=node.lat + offset_lat,
            lon=node.lon + offset_lon,
            tags={"natural": "tree"},
        )
        trees.append(tree)
        tree_id += 1

    return trees
