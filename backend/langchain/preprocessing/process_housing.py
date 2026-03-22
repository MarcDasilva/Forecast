from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import urlopen

TARGET_MUNICIPALITIES = ("KITCHENER", "WATERLOO", "CAMBRIDGE")
DEFAULT_BOUNDARIES_PATH = Path(__file__).with_name("boundaries.json")
DATASET_PRESETS = {
    "housing": {
        "label": "Housing",
        "url": (
            "https://services1.arcgis.com/qAo1OsXi67t7XgmS/arcgis/rest/services/"
            "Addresses/FeatureServer/0/query?where=1%3D1&outFields=*&outSR=4326&f=json"
        ),
    },
    "cambridge_locations": {
        "label": "Cambridge Locations",
        "url": (
            "https://maps.cambridge.ca/arcgispub03/rest/services/OpenData2/MapServer/10/query"
            "?where=1%3D1&outFields=*&outSR=4326&f=json"
        ),
    },
    "older_adult_housing": {
        "label": "Older Adult Housing Directory",
        "url": (
            "https://services.arcgis.com/ZpeBVw5o1kjit7LT/arcgis/rest/services/"
            "Older_Adult_Housing_Directory/FeatureServer/0/query"
            "?where=1%3D1&outFields=*&outSR=4326&f=json"
        ),
    },
    "hospitals": {
        "label": "Hospitals",
        "url": (
            "https://services1.arcgis.com/qAo1OsXi67t7XgmS/arcgis/rest/services/"
            "Hospitals/FeatureServer/0/query?where=1%3D1&outFields=*&outSR=4326&f=json"
        ),
    },
}


def build_query_url(base_url: str, **params: Any) -> str:
    parsed = urlparse(base_url)
    existing_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    normalized_params = {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in params.items()
    }
    query = urlencode({**existing_params, **normalized_params})
    return urlunparse(parsed._replace(query=query))


def fetch_json(url: str) -> dict[str, Any]:
    with urlopen(url) as response:
        return json.load(response)


def extract_target_polygons(
    boundaries_path: Path,
) -> dict[str, list[list[list[tuple[float, float]]]]]:
    data = json.loads(boundaries_path.read_text(encoding="utf-8"))
    polygons: dict[str, list[list[list[tuple[float, float]]]]] = {}

    for feature in data.get("features", []):
        properties = feature.get("properties", {})
        municipality = (
            properties.get("MUNICIPALITY")
            or properties.get("OFFICIAL_MUNICIPAL_NAME")
            or properties.get("LTIER")
        )
        if municipality not in TARGET_MUNICIPALITIES:
            continue

        geometry = feature.get("geometry", {})
        polygons[municipality] = flatten_polygon_rings(geometry)

    missing = [name for name in TARGET_MUNICIPALITIES if name not in polygons]
    if missing:
        raise ValueError(
            f"Missing municipality boundary data for: {', '.join(missing)} in {boundaries_path}"
        )

    return polygons


def flatten_polygon_rings(geometry: dict[str, Any]) -> list[list[list[tuple[float, float]]]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])

    if geometry_type == "Polygon":
        return [[to_ring(ring) for ring in coordinates]]
    if geometry_type == "MultiPolygon":
        return [[to_ring(ring) for ring in polygon] for polygon in coordinates]

    raise ValueError(f"Unsupported geometry type: {geometry_type}")


def to_ring(raw_ring: list[list[float]]) -> list[tuple[float, float]]:
    return [(float(point[0]), float(point[1])) for point in raw_ring]


def point_in_ring(x: float, y: float, ring: list[tuple[float, float]]) -> bool:
    inside = False
    if len(ring) < 3:
        return False

    for index in range(len(ring)):
        x1, y1 = ring[index]
        x2, y2 = ring[(index + 1) % len(ring)]
        intersects = ((y1 > y) != (y2 > y)) and (
            x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1
        )
        if intersects:
            inside = not inside

    return inside


def point_in_polygon(x: float, y: float, polygon: list[list[tuple[float, float]]]) -> bool:
    if not polygon:
        return False

    outer_ring, *holes = polygon
    if not point_in_ring(x, y, outer_ring):
        return False

    return not any(point_in_ring(x, y, hole) for hole in holes)


def find_municipality(
    x: float,
    y: float,
    municipality_polygons: dict[str, list[list[list[tuple[float, float]]]]],
) -> str | None:
    for municipality, polygons in municipality_polygons.items():
        if any(point_in_polygon(x, y, polygon) for polygon in polygons):
            return municipality
    return None


def detect_object_id_field(payload: dict[str, Any]) -> str:
    explicit_name = payload.get("objectIdFieldName")
    if explicit_name:
        return explicit_name

    unique_id_field = payload.get("uniqueIdField") or {}
    unique_name = unique_id_field.get("name")
    if unique_name:
        return unique_name

    for field in payload.get("fields", []):
        if field.get("type") == "esriFieldTypeOID":
            name = field.get("name")
            if name:
                return str(name)

    return "OBJECTID"


def fetch_page(
    api_url: str,
    object_id_field: str,
    page_size: int,
    result_offset: int,
) -> dict[str, Any]:
    page_url = build_query_url(
        api_url,
        outFields=object_id_field,
        returnGeometry=True,
        outSR=4326,
        resultOffset=result_offset,
        resultRecordCount=page_size,
        orderByFields=f"{object_id_field} ASC",
        f="json",
    )
    return fetch_json(page_url)


def count_points_by_municipality(
    api_url: str,
    municipality_polygons: dict[str, list[list[list[tuple[float, float]]]]],
    batch_size: int = 2000,
) -> dict[str, int]:
    counts = {municipality: 0 for municipality in TARGET_MUNICIPALITIES}
    first_page = fetch_json(
        build_query_url(
            api_url,
            returnGeometry=True,
            outSR=4326,
            resultOffset=0,
            resultRecordCount=batch_size,
            f="json",
        )
    )
    object_id_field = detect_object_id_field(first_page)
    result_offset = 0
    payload = first_page

    while True:
        features = payload.get("features", [])
        if not features:
            break

        for feature in features:
            geometry = feature.get("geometry") or {}
            x = geometry.get("x")
            y = geometry.get("y")
            if x is None or y is None:
                continue

            municipality = find_municipality(float(x), float(y), municipality_polygons)
            if municipality in counts:
                counts[municipality] += 1

        if not payload.get("exceededTransferLimit"):
            break

        result_offset += len(features)
        payload = fetch_page(
            api_url=api_url,
            object_id_field=object_id_field,
            page_size=batch_size,
            result_offset=result_offset,
        )

    return counts


def build_output(dataset: str, label: str, api_url: str, counts: dict[str, int]) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "label": label,
        "source": api_url,
        "regions": {
            "Kitchener": counts["KITCHENER"],
            "Waterloo": counts["WATERLOO"],
            "Cambridge": counts["CAMBRIDGE"],
        },
        "total_counted": sum(counts.values()),
    }


def run_dataset(
    dataset: str,
    api_url: str,
    label: str,
    boundaries_path: Path,
    batch_size: int,
) -> dict[str, Any]:
    municipality_polygons = extract_target_polygons(boundaries_path)
    counts = count_points_by_municipality(
        api_url=api_url,
        municipality_polygons=municipality_polygons,
        batch_size=batch_size,
    )
    return build_output(dataset=dataset, label=label, api_url=api_url, counts=counts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Count ArcGIS point features by Kitchener, Waterloo, and Cambridge using "
            "point-in-polygon checks against local municipal boundaries."
        )
    )
    parser.add_argument(
        "--dataset",
        choices=sorted(DATASET_PRESETS),
        help="Named dataset preset to run.",
    )
    parser.add_argument("--api-url", help="Custom ArcGIS query URL for a point layer.")
    parser.add_argument("--label", help="Human-readable label for a custom API URL.")
    parser.add_argument("--boundaries", type=Path, default=DEFAULT_BOUNDARIES_PATH)
    parser.add_argument("--output", type=Path, help="Optional file path for the JSON result.")
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument(
        "--all-presets",
        action="store_true",
        help="Run all built-in dataset presets and output a JSON array.",
    )
    return parser.parse_args()


def resolve_datasets(args: argparse.Namespace) -> list[tuple[str, str, str]]:
    if args.all_presets:
        return [
            (dataset, preset["url"], preset["label"])
            for dataset, preset in DATASET_PRESETS.items()
        ]

    if args.dataset:
        preset = DATASET_PRESETS[args.dataset]
        return [(args.dataset, preset["url"], preset["label"])]

    if args.api_url:
        return [("custom", args.api_url, args.label or "Custom Dataset")]

    preset = DATASET_PRESETS["housing"]
    return [("housing", preset["url"], preset["label"])]


def main() -> None:
    args = parse_args()
    datasets = resolve_datasets(args)
    outputs = [
        run_dataset(
            dataset=dataset,
            api_url=api_url,
            label=label,
            boundaries_path=args.boundaries,
            batch_size=args.batch_size,
        )
        for dataset, api_url, label in datasets
    ]

    final_output: dict[str, Any] | list[dict[str, Any]]
    if len(outputs) == 1:
        final_output = outputs[0]
    else:
        final_output = outputs

    output_json = json.dumps(final_output, indent=2)
    if args.output:
        args.output.write_text(output_json + "\n", encoding="utf-8")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
