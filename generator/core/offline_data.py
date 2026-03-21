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
            # South end - Fort Lee, NJ interchange
            (40.8474, -73.9637),
            (40.8550, -73.9680),
            (40.8630, -73.9710),
            (40.8720, -73.9740),
            (40.8800, -73.9760),
            (40.8880, -73.9780),
            (40.8960, -73.9800),
            (40.9040, -73.9815),
            # Alpine area
            (40.9130, -73.9830),
            (40.9220, -73.9845),
            # State Line Lookout area
            (40.9330, -73.9860),
            (40.9430, -73.9870),
            (40.9530, -73.9875),
            (40.9640, -73.9880),
            (40.9750, -73.9885),
            (40.9870, -73.9890),
            (41.0000, -73.9895),
            (41.0110, -73.9900),
            (41.0230, -73.9905),
            (41.0340, -73.9910),
            (41.0450, -73.9915),
            (41.0560, -73.9920),
            # North end - NY state line
            (41.0700, -73.9930),
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
