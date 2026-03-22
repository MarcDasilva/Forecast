from __future__ import annotations

from forecast.scoring.benchmarks import (
    IMPORTANCE_WEIGHTS,
    evaluate_employment,
    explain_benchmark,
    evaluate_healthcare,
    evaluate_transportation,
)


def test_importance_weights_sum_to_one() -> None:
    assert sum(IMPORTANCE_WEIGHTS.values()) == 1.0


def test_evaluate_healthcare_uses_expected_metrics() -> None:
    score = evaluate_healthcare(
        {
            "hospital_beds_per_1000": 3.0,
            "primary_care_physicians_per_1000": 1.0,
            "emergency_response_time_min": 8.0,
            "preventable_hospitalizations_per_100k": 150.0,
        }
    )
    assert score == 0.75


def test_evaluate_transportation_rewards_strong_metrics() -> None:
    score = evaluate_transportation(
        {
            "transit_modal_share_pct": 50.0,
            "average_commute_time_min": 30.0,
            "cycling_modal_share_pct": 10.0,
            "road_fatality_rate_per_10000_vehicles": 0.0,
        }
    )
    assert score == 1.0


def test_evaluators_accept_aggregated_metric_suffixes() -> None:
    score = evaluate_healthcare(
        {
            "hospital_beds_per_1000_avg": 3.0,
            "primary_care_physicians_per_1000_avg": 1.0,
            "emergency_response_time_min_avg": 8.0,
            "preventable_hospitalizations_per_100k_avg": 150.0,
        }
    )
    assert score == 0.75


def test_evaluate_employment_is_conservative_on_mixed_metrics() -> None:
    score = evaluate_employment(
        {
            "unemployment_rate": 5.5,
            "living_wage_compliance_pct": 65.0,
            "labour_force_participation_pct": 60.0,
            "gini_coefficient": 0.35,
        }
    )
    assert round(score, 4) == 0.7346


def test_explain_benchmark_returns_component_breakdown() -> None:
    explanation = explain_benchmark(
        "healthcare",
        {
            "hospital_beds_per_1000": 3.0,
            "primary_care_physicians_per_1000": 1.0,
            "emergency_response_time_min": 8.0,
            "preventable_hospitalizations_per_100k": 150.0,
        },
    )

    assert explanation["category"] == "healthcare"
    assert explanation["metric_count"] == 4
    assert explanation["benchmark_eval"] == 0.75
    assert [component["metric"] for component in explanation["components"]] == [
        "hospital_beds_per_capita",
        "emergency_response_time",
        "primary_care_coverage",
        "preventable_hospitalisation",
    ]
