"""Validación de los casos y fixtures de evals."""

import json

import yaml

from evals.run_evals import EVALS_DIR


def test_cases_file_has_sixty_unique_cases():
    cases = yaml.safe_load((EVALS_DIR / "cases.yaml").read_text())

    assert len(cases) == 60
    assert len({case["id"] for case in cases}) == 60
    assert all(case.get("question") for case in cases)
    assert all("expect" in case for case in cases)


def test_all_referenced_fixtures_exist():
    cases = yaml.safe_load((EVALS_DIR / "cases.yaml").read_text())

    for case in cases:
        fixture = case.get("weather_fixture")
        if fixture:
            assert (EVALS_DIR / fixture).is_file(), case["id"]


def test_fixtures_have_expected_shape():
    for fixture in (EVALS_DIR / "fixtures").glob("*.json"):
        payload = json.loads(fixture.read_text())
        assert payload["locations"], fixture.name
        for location in payload["locations"].values():
            assert location["current"]["location"]
            assert location["forecast"]
            assert location["history"]
