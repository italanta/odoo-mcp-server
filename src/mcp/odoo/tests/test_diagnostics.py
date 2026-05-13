import pytest

from src.mcp.odoo.utils.diagnostics import diagnose_odoo_call


class TestDiagnoseOdooCall:
    def test_classifies_read_only_method(self):
        result = diagnose_odoo_call(model="crm.lead", method="search_read")

        assert result["success"] is True
        assert result["classification"]["safety"] == "read_only"
        assert result["issues"] == []
        assert result["suggested_payload"] == {
            "model": "crm.lead",
            "method": "search_read",
            "args": [],
            "kwargs": {},
        }

    def test_flags_destructive_write_without_expected_args(self):
        result = diagnose_odoo_call(model="crm.lead", method="write", args=[[1, 2]])

        assert result["success"] is False
        assert result["classification"]["safety"] == "destructive"
        codes = {issue["code"] for issue in result["issues"]}
        assert "destructive_method" in codes
        assert "write_args_shape" in codes

    def test_flags_invalid_model_and_missing_method(self):
        result = diagnose_odoo_call(model="crm lead", method="")

        assert result["success"] is False
        codes = {issue["code"] for issue in result["issues"]}
        assert "invalid_model_name" in codes
        assert "missing_method" in codes

    def test_classifies_side_effect_patterns(self):
        result = diagnose_odoo_call(model="crm.lead", method="action_send_mail")

        assert result["success"] is True
        assert result["classification"]["safety"] == "side_effect"
        assert result["classification"]["side_effect_method"] is True
        assert result["issues"][0]["code"] == "side_effect_method"

    @pytest.mark.parametrize("args, kwargs", [(None, None), ([], None), (None, {})])
    def test_normalizes_optional_args_and_kwargs(self, args, kwargs):
        result = diagnose_odoo_call(model="project.task", method="read", args=args, kwargs=kwargs)

        assert result["suggested_payload"]["args"] == []
        assert result["suggested_payload"]["kwargs"] == {}
