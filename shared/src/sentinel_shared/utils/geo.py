from __future__ import annotations

from datetime import datetime
from math import asin, cos, radians, sin, sqrt


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)
    start = (
        sin(delta_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(delta_lon / 2) ** 2
    )
    return 2 * radius_km * asin(sqrt(start))


def is_impossible_travel(
    previous_lat: float | None,
    previous_lon: float | None,
    previous_timestamp: datetime | None,
    current_lat: float | None,
    current_lon: float | None,
    current_timestamp: datetime,
    threshold_kmh: float = 900.0,
) -> bool:
    if None in {previous_lat, previous_lon, current_lat, current_lon} or previous_timestamp is None:
        return False
    assert previous_lat is not None
    assert previous_lon is not None
    assert current_lat is not None
    assert current_lon is not None
    distance = haversine_km(previous_lat, previous_lon, current_lat, current_lon)
    hours = max((current_timestamp - previous_timestamp).total_seconds() / 3600, 0.001)
    return (distance / hours) > threshold_kmh
