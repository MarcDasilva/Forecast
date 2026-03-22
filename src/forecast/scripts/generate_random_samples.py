from __future__ import annotations

import csv
import random
from pathlib import Path


OUTPUT_DIR = Path("data/samples/generated")


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def generate_housing(index: int, rng: random.Random) -> tuple[str, Path]:
    rows = []
    for row_index in range(5):
        rows.append(
            {
                "block_id": f"H-{index}-{row_index + 1}",
                "city": "Toronto",
                "reporting_period": "2025-Q4",
                "vacancy_rate": round(rng.uniform(3.2, 5.9), 2),
                "cost_burden_pct": round(rng.uniform(30.0, 44.0), 2),
                "new_housing_starts_per_1000_residents": round(rng.uniform(5.2, 9.6), 2),
                "housing_density_units_per_hectare": round(rng.uniform(26.0, 48.0), 2),
            }
        )
    path = OUTPUT_DIR / f"housing_{index:02d}.csv"
    write_csv(path, list(rows[0].keys()), rows)
    return "housing", path


def generate_transportation(index: int, rng: random.Random) -> tuple[str, Path]:
    rows = []
    for row_index in range(5):
        rows.append(
            {
                "segment_id": f"T-{index}-{row_index + 1}",
                "city": "Toronto",
                "reporting_period": "2025-Q4",
                "transit_modal_share_pct": round(rng.uniform(42.0, 56.0), 2),
                "average_commute_time_min": round(rng.uniform(28.0, 38.0), 2),
                "cycling_modal_share_pct": round(rng.uniform(6.0, 12.0), 2),
                "road_fatality_rate_per_10000_vehicles": round(rng.uniform(0.6, 1.4), 2),
                "walkability_score": round(rng.uniform(72.0, 88.0), 1),
            }
        )
    path = OUTPUT_DIR / f"transportation_{index:02d}.csv"
    write_csv(path, list(rows[0].keys()), rows)
    return "transportation", path


def generate_healthcare(index: int, rng: random.Random) -> tuple[str, Path]:
    rows = []
    for row_index in range(5):
        rows.append(
            {
                "facility_id": f"HC-{index}-{row_index + 1}",
                "city": "Toronto",
                "reporting_period": "2025-Q4",
                "hospital_beds_per_1000": round(rng.uniform(2.4, 3.5), 2),
                "primary_care_physicians_per_1000": round(rng.uniform(0.82, 1.15), 2),
                "emergency_response_time_min": round(rng.uniform(7.2, 9.7), 2),
                "preventable_hospitalizations_per_100k": round(rng.uniform(132.0, 185.0), 1),
                "vaccination_coverage_pct": round(rng.uniform(84.0, 93.0), 2),
            }
        )
    path = OUTPUT_DIR / f"healthcare_{index:02d}.csv"
    write_csv(path, list(rows[0].keys()), rows)
    return "healthcare", path


def generate_employment(index: int, rng: random.Random) -> tuple[str, Path]:
    rows = []
    for row_index in range(5):
        rows.append(
            {
                "district_id": f"E-{index}-{row_index + 1}",
                "city": "Toronto",
                "reporting_period": "2025-Q4",
                "unemployment_rate": round(rng.uniform(4.1, 7.4), 2),
                "living_wage_compliance_pct": round(rng.uniform(58.0, 82.0), 2),
                "labour_force_participation_pct": round(rng.uniform(55.0, 68.0), 2),
                "gini_coefficient": round(rng.uniform(0.29, 0.41), 3),
                "median_household_income": round(rng.uniform(64000, 96000), 0),
            }
        )
    path = OUTPUT_DIR / f"employment_{index:02d}.csv"
    write_csv(path, list(rows[0].keys()), rows)
    return "employment", path


def generate_placemaking(index: int, rng: random.Random) -> tuple[str, Path]:
    rows = []
    for row_index in range(5):
        rows.append(
            {
                "neighbourhood_id": f"P-{index}-{row_index + 1}",
                "city": "Toronto",
                "reporting_period": "2025-Q4",
                "green_space_per_capita": round(rng.uniform(6.0, 12.5), 2),
                "park_access_pct": round(rng.uniform(68.0, 92.0), 2),
                "cultural_venue_density": round(rng.uniform(0.14, 0.32), 3),
                "neighbourhood_satisfaction_pct": round(rng.uniform(61.0, 83.0), 2),
                "community_centre_usage_pct": round(rng.uniform(42.0, 78.0), 2),
            }
        )
    path = OUTPUT_DIR / f"placemaking_{index:02d}.csv"
    write_csv(path, list(rows[0].keys()), rows)
    return "placemaking", path


def main() -> None:
    rng = random.Random(20260322)
    generators = [
        generate_housing,
        generate_transportation,
        generate_healthcare,
        generate_employment,
        generate_placemaking,
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for existing in OUTPUT_DIR.glob("*.csv"):
        existing.unlink()

    generated: list[tuple[str, Path]] = []
    for index in range(10):
        generator = generators[index % len(generators)]
        generated.append(generator(index + 1, rng))

    for expected_category, path in generated:
        print(f"{expected_category}:{path}")


if __name__ == "__main__":
    main()
