import math
import xml.etree.ElementTree as ElementTree
from typing import Any

from .internal_feeds import (
    TROPICAL_CYCLONE_TRACK_AREA_DATASET,
    TROPICAL_CYCLONE_TRACK_DATASET,
)
from .storage_read import StoredDataError


def tropical_cyclone_geo_json(payload: bytes) -> dict[str, Any]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        raise StoredDataError(TROPICAL_CYCLONE_TRACK_DATASET) from error

    features = []
    for placemark in root.iter():
        if placemark.tag.rpartition("}")[2] != "Placemark":
            continue
        properties: dict[str, Any] = {"model": "HKO Official"}
        for child in placemark:
            local_name = child.tag.rpartition("}")[2]
            if local_name in {"name", "description", "styleUrl"} and child.text:
                properties[local_name] = child.text.strip()
        for element in placemark.iter():
            local_name = element.tag.rpartition("}")[2]
            if local_name not in {"Data", "SimpleData"}:
                continue
            field_name = element.attrib.get("name")
            value_element = next(
                (
                    child
                    for child in element
                    if child.tag.rpartition("}")[2] == "value" and child.text
                ),
                None,
            )
            field_value = (
                value_element.text.strip()
                if value_element is not None and value_element.text
                else element.text.strip()
                if element.text
                else ""
            )
            if field_name and field_value:
                properties[field_name] = field_value
                if "model" in field_name.lower():
                    properties["model"] = field_value

        for element in placemark.iter():
            geometry_type = element.tag.rpartition("}")[2]
            if geometry_type not in {"Point", "LineString", "LinearRing"}:
                continue
            coordinate_element = next(
                (
                    child
                    for child in element.iter()
                    if child.tag.rpartition("}")[2] == "coordinates" and child.text
                ),
                None,
            )
            if coordinate_element is None:
                continue
            try:
                coordinates = [
                    [float(item) for item in token.split(",")][:3]
                    for token in coordinate_element.text.split()
                ]
                if any(len(item) < 2 for item in coordinates):
                    raise ValueError("coordinate has too few values")
            except ValueError as error:
                raise StoredDataError(TROPICAL_CYCLONE_TRACK_DATASET) from error
            if not coordinates:
                continue
            geo_type = "Point" if geometry_type == "Point" else "LineString"
            features.append(
                {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": geo_type,
                        "coordinates": (
                            coordinates[0] if geo_type == "Point" else coordinates
                        ),
                    },
                }
            )
    if not features:
        raise StoredDataError(TROPICAL_CYCLONE_TRACK_DATASET)
    return {"type": "FeatureCollection", "features": features}


def tropical_cyclone_track_area_geo_json(payload: bytes) -> dict[str, Any]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        raise StoredDataError(TROPICAL_CYCLONE_TRACK_AREA_DATASET) from error

    periods = {
        "#error_cone_0_": "0-72 hours",
        "#error_cone_1_": "72-120 hours",
    }
    features = []
    for placemark in root.iter():
        if placemark.tag.rpartition("}")[2] != "Placemark":
            continue
        style_url = next(
            (
                child.text.strip()
                for child in placemark
                if child.tag.rpartition("}")[2] == "styleUrl" and child.text
            ),
            "",
        )
        forecast_period = periods.get(style_url)
        if forecast_period is None:
            continue
        coordinate_element = next(
            (
                element
                for element in placemark.iter()
                if element.tag.rpartition("}")[2] == "coordinates"
                and element.text
                and element.text.strip()
            ),
            None,
        )
        if coordinate_element is None:
            raise StoredDataError(TROPICAL_CYCLONE_TRACK_AREA_DATASET)
        try:
            coordinates = [
                [float(item) for item in token.split(",")][:3]
                for token in coordinate_element.text.split()
            ]
            if any(len(item) < 2 for item in coordinates):
                raise ValueError("coordinate has too few values")
        except ValueError as error:
            raise StoredDataError(TROPICAL_CYCLONE_TRACK_AREA_DATASET) from error
        points = [tuple(coordinate[:2]) for coordinate in coordinates]
        if (
            len(coordinates) < 4
            or any(
                len(point) != 2
                or not all(math.isfinite(value) for value in point)
                for point in points
            )
            or len(set(points)) < 3
        ):
            raise StoredDataError(TROPICAL_CYCLONE_TRACK_AREA_DATASET)
        if coordinates[0][:2] != coordinates[-1][:2]:
            coordinates.append(coordinates[0].copy())
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "model": "HKO Official",
                    "forecastPeriod": forecast_period,
                    "probability": 0.7,
                    "styleUrl": style_url,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [coordinates],
                },
            }
        )
    if not features:
        raise StoredDataError(TROPICAL_CYCLONE_TRACK_AREA_DATASET)
    return {"type": "FeatureCollection", "features": features}
