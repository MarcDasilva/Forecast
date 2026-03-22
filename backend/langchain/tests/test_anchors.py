from __future__ import annotations

from forecast.scoring.anchors import ANCHOR_TEXTS, get_anchor_categories


def test_anchor_categories_match_expected_set() -> None:
    assert set(get_anchor_categories()) == {
        "housing",
        "transportation",
        "healthcare",
        "employment",
        "placemaking",
    }


def test_anchor_texts_are_present_for_all_categories() -> None:
    for category in get_anchor_categories():
        assert category in ANCHOR_TEXTS
        assert ANCHOR_TEXTS[category]
