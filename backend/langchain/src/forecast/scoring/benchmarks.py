from __future__ import annotations

from collections.abc import Iterable


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


IMPORTANCE_WEIGHTS: dict[str, float] = {
    "housing": 0.25,
    "employment": 0.25,
    "transportation": 0.20,
    "healthcare": 0.20,
    "placemaking": 0.10,
}


METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "housing_cost_burden": ("housing_cost_burden_pct", "cost_burden_pct"),
    "housing_density": ("housing_density", "housing_density_units_per_hectare"),
    "vacancy_rate": ("vacancy_rate",),
    "new_housing_starts": ("new_housing_starts_per_1000_residents", "new_housing_starts"),
    "transit_modal_share": ("transit_modal_share_pct", "transit_modal_share"),
    "average_commute_time": ("average_commute_time_min", "average_commute_time"),
    "road_fatality_rate": (
        "road_fatality_rate_per_10000_vehicles",
        "road_fatality_rate",
    ),
    "cycling_modal_share": ("cycling_modal_share_pct", "cycling_modal_share"),
    "hospital_beds_per_capita": ("hospital_beds_per_1000", "hospital_beds_per_capita"),
    "emergency_response_time": ("emergency_response_time_min", "emergency_response_time"),
    "primary_care_coverage": (
        "primary_care_physicians_per_1000",
        "primary_care_coverage",
        "gp_per_1000",
    ),
    "preventable_hospitalisation": (
        "preventable_hospitalizations_per_100k",
        "preventable_hospitalisation",
    ),
    "unemployment_rate": ("unemployment_rate",),
    "living_wage_compliance": ("living_wage_compliance_pct", "living_wage_compliance"),
    "labour_force_participation": (
        "labour_force_participation_pct",
        "labour_force_participation",
    ),
    "gini_coefficient": ("gini_coefficient",),
    "green_space_per_capita": ("green_space_per_capita",),
    "park_access": ("park_access_pct", "park_access"),
    "cultural_venue_density": ("cultural_venue_density",),
    "neighbourhood_satisfaction": (
        "neighbourhood_satisfaction_pct",
        "neighbourhood_satisfaction",
    ),
}


AGGREGATE_SUFFIXES = ("_avg", "_mean", "_median")


def normalize_metric_key(metric_key: str) -> str:
    for suffix in AGGREGATE_SUFFIXES:
        if metric_key.endswith(suffix):
            return metric_key[: -len(suffix)]
    return metric_key


def get_metric(metrics: dict[str, float | None], alias_key: str) -> float | None:
    normalized_metrics = {
        normalize_metric_key(metric_name): value
        for metric_name, value in metrics.items()
    }
    for alias in METRIC_ALIASES[alias_key]:
        value = metrics.get(alias)
        if value is not None:
            return float(value)
        value = normalized_metrics.get(alias)
        if value is not None:
            return float(value)
    return None


def average_scores(scores: Iterable[float]) -> float:
    values = list(scores)
    if not values:
        return 0.0
    return sum(values) / len(values)


def evaluate_housing(metrics: dict[str, float | None]) -> float:
    scores: list[float] = []
    cost_burden = get_metric(metrics, "housing_cost_burden")
    if cost_burden is not None:
        scores.append(clamp(1 - (cost_burden / 30)))
    density = get_metric(metrics, "housing_density")
    if density is not None:
        scores.append(clamp(density / 40))
    vacancy = get_metric(metrics, "vacancy_rate")
    if vacancy is not None:
        scores.append(clamp(1 - abs(vacancy - 6.5) / 6.5))
    starts = get_metric(metrics, "new_housing_starts")
    if starts is not None:
        scores.append(clamp(starts / 10))
    return average_scores(scores)


def evaluate_transportation(metrics: dict[str, float | None]) -> float:
    scores: list[float] = []
    transit = get_metric(metrics, "transit_modal_share")
    if transit is not None:
        scores.append(clamp(transit / 50))
    commute = get_metric(metrics, "average_commute_time")
    if commute is not None:
        scores.append(clamp(1 - max(commute - 30, 0) / 30))
    fatality = get_metric(metrics, "road_fatality_rate")
    if fatality is not None:
        scores.append(clamp(1 - fatality / 1))
    cycling = get_metric(metrics, "cycling_modal_share")
    if cycling is not None:
        scores.append(clamp(cycling / 10))
    return average_scores(scores)


def evaluate_healthcare(metrics: dict[str, float | None]) -> float:
    scores: list[float] = []
    beds = get_metric(metrics, "hospital_beds_per_capita")
    if beds is not None:
        scores.append(clamp(beds / 3))
    response = get_metric(metrics, "emergency_response_time")
    if response is not None:
        scores.append(clamp(1 - max(response - 8, 0) / 8))
    coverage = get_metric(metrics, "primary_care_coverage")
    if coverage is not None:
        scores.append(clamp(coverage / 1))
    preventable = get_metric(metrics, "preventable_hospitalisation")
    if preventable is not None:
        scores.append(clamp(1 - preventable / 150))
    return average_scores(scores)


def evaluate_employment(metrics: dict[str, float | None]) -> float:
    scores: list[float] = []
    unemployment = get_metric(metrics, "unemployment_rate")
    if unemployment is not None:
        scores.append(clamp(1 - max(unemployment - 4, 0) / 4))
    living_wage = get_metric(metrics, "living_wage_compliance")
    if living_wage is not None:
        scores.append(clamp(living_wage / 80))
    participation = get_metric(metrics, "labour_force_participation")
    if participation is not None:
        scores.append(clamp(participation / 65))
    gini = get_metric(metrics, "gini_coefficient")
    if gini is not None:
        scores.append(clamp(1 - max(gini - 0.30, 0) / 0.30))
    return average_scores(scores)


def evaluate_placemaking(metrics: dict[str, float | None]) -> float:
    scores: list[float] = []
    green = get_metric(metrics, "green_space_per_capita")
    if green is not None:
        scores.append(clamp(green / 9))
    park_access = get_metric(metrics, "park_access")
    if park_access is not None:
        scores.append(clamp(park_access / 85))
    cultural = get_metric(metrics, "cultural_venue_density")
    if cultural is not None:
        scores.append(clamp(cultural))
    satisfaction = get_metric(metrics, "neighbourhood_satisfaction")
    if satisfaction is not None:
        scores.append(clamp(satisfaction / 75))
    return average_scores(scores)


BENCHMARK_EVALUATORS = {
    "housing": evaluate_housing,
    "transportation": evaluate_transportation,
    "healthcare": evaluate_healthcare,
    "employment": evaluate_employment,
    "placemaking": evaluate_placemaking,
}
