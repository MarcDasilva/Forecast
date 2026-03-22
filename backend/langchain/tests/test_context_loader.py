from forecast.agents.context_loader import SPECIALIST_CATEGORIES, load_category_context


def test_load_category_context_returns_split_files() -> None:
    assert SPECIALIST_CATEGORIES == (
        "housing",
        "employment",
        "transportation",
        "healthcare",
        "placemaking",
    )

    housing_context = load_category_context("housing")
    healthcare_context = load_category_context("healthcare")

    assert "Housing Supply" in housing_context
    assert "Functional Zero Chronic Homelessness by 2030" in housing_context
    assert "Primary Care Access" in healthcare_context
    assert "family doctor" in healthcare_context
