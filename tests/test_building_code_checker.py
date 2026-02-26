"""Additional tests for the building code compliance helpers."""

import pytest
from tools import checker_building_code as bcc

REQUIRED_KEYS = {
    "element_id",
    "element_type",
    "element_name",
    "element_name_long",
    "check_status",
    "actual_value",
    "required_value",
    "comment",
    "log",
}


def _validate_result_list(results):
    assert isinstance(results, list), "Result should be a list"
    for item in results:
        assert isinstance(item, dict), f"Item {item} is not a dict"
        missing = REQUIRED_KEYS - set(item.keys())
        assert not missing, f"Missing keys in result item: {missing}"
        assert item.get("check_status") in {"pass", "fail", "warning", "blocked", "log"}


class TestBuildingCodeFunctions:
    def test_space_compliance_returns_sensible(self, simple_ifc_model):
        results = bcc.check_space_compliance(simple_ifc_model)
        _validate_result_list(results)
        # there should be at least one space result even for simple model
        assert len(results) >= 1

    def test_window_compliance_returns_sensible(self, simple_ifc_model):
        results = bcc.analyze_window_compliance(simple_ifc_model)
        _validate_result_list(results)
        # one entry per space
        spaces = [r for r in results if r.get("element_type") == "IfcSpace"]
        assert len(spaces) >= 1

    def test_evacuation_routes_returns_summary(self, simple_ifc_model):
        results = bcc.analyze_evacuation_routes(simple_ifc_model)
        _validate_result_list(results)
        # expect at least one summary entry for the route distance
        summ = [r for r in results if r.get("element_type") == "EvacuationSummary"]
        assert summ, "Evacuation summary missing"

    def test_functions_handle_empty_model(self, empty_ifc_model):
        for func in (
            bcc.check_space_compliance,
            bcc.analyze_window_compliance,
            bcc.analyze_evacuation_routes,
        ):
            # should not raise and should return an empty or minimal list
            res = func(empty_ifc_model)
            assert isinstance(res, list)
