from __future__ import annotations

from collections.abc import Iterable
from typing import Any


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


def _friendly_metric_label(metric_name: str) -> str:
    return metric_name.replace("_", " ").title()


def _metric_component(
    *,
    metric_name: str,
    raw_value: float,
    normalized_score: float,
    formula: str,
    interpretation: str,
) -> dict[str, Any]:
    return {
        "metric": metric_name,
        "label": _friendly_metric_label(metric_name),
        "raw_value": float(raw_value),
        "normalized_score": float(normalized_score),
        "formula": formula,
        "interpretation": interpretation,
    }


def _housing_components(metrics: dict[str, float | None]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    cost_burden = get_metric(metrics, "housing_cost_burden")
    if cost_burden is not None:
        components.append(
            _metric_component(
                metric_name="housing_cost_burden",
                raw_value=cost_burden,
                normalized_score=clamp(1 - (cost_burden / 30)),
                formula="clamp(1 - (housing_cost_burden / 30))",
                interpretation="Lower housing cost burden improves the benchmark score.",
            )
        )
    density = get_metric(metrics, "housing_density")
    if density is not None:
        components.append(
            _metric_component(
                metric_name="housing_density",
                raw_value=density,
                normalized_score=clamp(density / 40),
                formula="clamp(housing_density / 40)",
                interpretation="Higher housing density improves the benchmark score.",
            )
        )
    vacancy = get_metric(metrics, "vacancy_rate")
    if vacancy is not None:
        components.append(
            _metric_component(
                metric_name="vacancy_rate",
                raw_value=vacancy,
                normalized_score=clamp(1 - abs(vacancy - 6.5) / 6.5),
                formula="clamp(1 - abs(vacancy_rate - 6.5) / 6.5)",
                interpretation="Vacancy performs best when it stays near the 6.5% target band.",
            )
        )
    starts = get_metric(metrics, "new_housing_starts")
    if starts is not None:
        components.append(
            _metric_component(
                metric_name="new_housing_starts",
                raw_value=starts,
                normalized_score=clamp(starts / 10),
                formula="clamp(new_housing_starts / 10)",
                interpretation="More housing starts improve the benchmark score.",
            )
        )
    return components


def _transportation_components(metrics: dict[str, float | None]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    transit = get_metric(metrics, "transit_modal_share")
    if transit is not None:
        components.append(
            _metric_component(
                metric_name="transit_modal_share",
                raw_value=transit,
                normalized_score=clamp(transit / 50),
                formula="clamp(transit_modal_share / 50)",
                interpretation="Higher transit modal share improves the benchmark score.",
            )
        )
    commute = get_metric(metrics, "average_commute_time")
    if commute is not None:
        components.append(
            _metric_component(
                metric_name="average_commute_time",
                raw_value=commute,
                normalized_score=clamp(1 - max(commute - 30, 0) / 30),
                formula="clamp(1 - max(average_commute_time - 30, 0) / 30)",
                interpretation="Shorter commutes improve the benchmark score once trips exceed 30 minutes.",
            )
        )
    fatality = get_metric(metrics, "road_fatality_rate")
    if fatality is not None:
        components.append(
            _metric_component(
                metric_name="road_fatality_rate",
                raw_value=fatality,
                normalized_score=clamp(1 - fatality / 1),
                formula="clamp(1 - road_fatality_rate / 1)",
                interpretation="Lower road fatality rates improve the benchmark score.",
            )
        )
    cycling = get_metric(metrics, "cycling_modal_share")
    if cycling is not None:
        components.append(
            _metric_component(
                metric_name="cycling_modal_share",
                raw_value=cycling,
                normalized_score=clamp(cycling / 10),
                formula="clamp(cycling_modal_share / 10)",
                interpretation="Higher cycling mode share improves the benchmark score.",
            )
        )
    return components


def _healthcare_components(metrics: dict[str, float | None]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    beds = get_metric(metrics, "hospital_beds_per_capita")
    if beds is not None:
        components.append(
            _metric_component(
                metric_name="hospital_beds_per_capita",
                raw_value=beds,
                normalized_score=clamp(beds / 3),
                formula="clamp(hospital_beds_per_capita / 3)",
                interpretation="More beds per capita improve the benchmark score.",
            )
        )
    response = get_metric(metrics, "emergency_response_time")
    if response is not None:
        components.append(
            _metric_component(
                metric_name="emergency_response_time",
                raw_value=response,
                normalized_score=clamp(1 - max(response - 8, 0) / 8),
                formula="clamp(1 - max(emergency_response_time - 8, 0) / 8)",
                interpretation="Faster emergency response improves the benchmark score after eight minutes.",
            )
        )
    coverage = get_metric(metrics, "primary_care_coverage")
    if coverage is not None:
        components.append(
            _metric_component(
                metric_name="primary_care_coverage",
                raw_value=coverage,
                normalized_score=clamp(coverage / 1),
                formula="clamp(primary_care_coverage / 1)",
                interpretation="Higher primary care coverage improves the benchmark score.",
            )
        )
    preventable = get_metric(metrics, "preventable_hospitalisation")
    if preventable is not None:
        components.append(
            _metric_component(
                metric_name="preventable_hospitalisation",
                raw_value=preventable,
                normalized_score=clamp(1 - preventable / 150),
                formula="clamp(1 - preventable_hospitalisation / 150)",
                interpretation="Lower preventable hospitalisation rates improve the benchmark score.",
            )
        )
    return components


def _employment_components(metrics: dict[str, float | None]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    unemployment = get_metric(metrics, "unemployment_rate")
    if unemployment is not None:
        components.append(
            _metric_component(
                metric_name="unemployment_rate",
                raw_value=unemployment,
                normalized_score=clamp(1 - max(unemployment - 4, 0) / 3.5),
                formula="clamp(1 - max(unemployment_rate - 4, 0) / 3.5)",
                interpretation="Lower unemployment improves the benchmark score once it rises above 4%.",
            )
        )
    living_wage = get_metric(metrics, "living_wage_compliance")
    if living_wage is not None:
        components.append(
            _metric_component(
                metric_name="living_wage_compliance",
                raw_value=living_wage,
                normalized_score=clamp(living_wage / 85),
                formula="clamp(living_wage_compliance / 85)",
                interpretation="Higher living-wage compliance improves the benchmark score.",
            )
        )
    participation = get_metric(metrics, "labour_force_participation")
    if participation is not None:
        components.append(
            _metric_component(
                metric_name="labour_force_participation",
                raw_value=participation,
                normalized_score=clamp(participation / 68),
                formula="clamp(labour_force_participation / 68)",
                interpretation="Higher labour force participation improves the benchmark score.",
            )
        )
    gini = get_metric(metrics, "gini_coefficient")
    if gini is not None:
        components.append(
            _metric_component(
                metric_name="gini_coefficient",
                raw_value=gini,
                normalized_score=clamp(1 - max(gini - 0.28, 0) / 0.25),
                formula="clamp(1 - max(gini_coefficient - 0.28, 0) / 0.25)",
                interpretation="Lower income inequality improves the benchmark score above the 0.28 reference point.",
            )
        )
    return components


def _placemaking_components(metrics: dict[str, float | None]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    green = get_metric(metrics, "green_space_per_capita")
    if green is not None:
        components.append(
            _metric_component(
                metric_name="green_space_per_capita",
                raw_value=green,
                normalized_score=clamp(green / 9),
                formula="clamp(green_space_per_capita / 9)",
                interpretation="More green space per capita improves the benchmark score.",
            )
        )
    park_access = get_metric(metrics, "park_access")
    if park_access is not None:
        components.append(
            _metric_component(
                metric_name="park_access",
                raw_value=park_access,
                normalized_score=clamp(park_access / 85),
                formula="clamp(park_access / 85)",
                interpretation="Higher park access improves the benchmark score.",
            )
        )
    cultural = get_metric(metrics, "cultural_venue_density")
    if cultural is not None:
        components.append(
            _metric_component(
                metric_name="cultural_venue_density",
                raw_value=cultural,
                normalized_score=clamp(cultural),
                formula="clamp(cultural_venue_density)",
                interpretation="Higher cultural venue density improves the benchmark score.",
            )
        )
    satisfaction = get_metric(metrics, "neighbourhood_satisfaction")
    if satisfaction is not None:
        components.append(
            _metric_component(
                metric_name="neighbourhood_satisfaction",
                raw_value=satisfaction,
                normalized_score=clamp(satisfaction / 75),
                formula="clamp(neighbourhood_satisfaction / 75)",
                interpretation="Higher neighbourhood satisfaction improves the benchmark score.",
            )
        )
    return components


BENCHMARK_COMPONENT_BUILDERS = {
    "housing": _housing_components,
    "transportation": _transportation_components,
    "healthcare": _healthcare_components,
    "employment": _employment_components,
    "placemaking": _placemaking_components,
}


def explain_benchmark(category: str, metrics: dict[str, float | None]) -> dict[str, Any]:
    components = BENCHMARK_COMPONENT_BUILDERS[category](metrics)
    benchmark_eval = average_scores(component["normalized_score"] for component in components)
    return {
        "category": category,
        "benchmark_eval": float(benchmark_eval),
        "metric_count": len(components),
        "benchmark_formula": "benchmark_eval = average(normalized metric component scores)",
        "components": components,
    }


def evaluate_housing(metrics: dict[str, float | None]) -> float:
    return average_scores(component["normalized_score"] for component in _housing_components(metrics))


def evaluate_transportation(metrics: dict[str, float | None]) -> float:
    return average_scores(component["normalized_score"] for component in _transportation_components(metrics))


def evaluate_healthcare(metrics: dict[str, float | None]) -> float:
    return average_scores(component["normalized_score"] for component in _healthcare_components(metrics))


def evaluate_employment(metrics: dict[str, float | None]) -> float:
    return average_scores(component["normalized_score"] for component in _employment_components(metrics))


def evaluate_placemaking(metrics: dict[str, float | None]) -> float:
    return average_scores(component["normalized_score"] for component in _placemaking_components(metrics))


BENCHMARK_EVALUATORS = {
    "housing": evaluate_housing,
    "transportation": evaluate_transportation,
    "healthcare": evaluate_healthcare,
    "employment": evaluate_employment,
    "placemaking": evaluate_placemaking,
}
