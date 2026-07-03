"""Streamlit AppTest for Bus Monitor dashboard.
Tests that pages load without exceptions and widget interactions work.
"""
from streamlit.testing.v1 import AppTest


def test_peta_langsung_loads():
    at = AppTest.from_file("pages/1_Peta_Langsung.py", default_timeout=10)
    at.run()
    assert not at.exception
    # KPI cards should render (4 columns)
    assert len(at.columns) >= 4
    # Multiselect should exist
    assert at.multiselect[0].label == "Route"


def test_peta_langsung_filters():
    at = AppTest.from_file("pages/1_Peta_Langsung.py", default_timeout=10)
    at.run()
    assert not at.exception
    # Change status filter
    at.selectbox[0].set_value("Live").run()
    assert not at.exception


def test_peta_langsung_multiselect_empty():
    """Bug #2: empty multiselect = show all, not crash."""
    at = AppTest.from_file("pages/1_Peta_Langsung.py", default_timeout=10)
    at.run()
    assert not at.exception
    # Default multiselect is empty (show all)
    assert at.multiselect[0].value == []


def test_jadwal_loads():
    at = AppTest.from_file("pages/2_Jadwal.py", default_timeout=30)
    at.run()
    assert not at.exception
    # Route selectbox exists
    assert at.selectbox[0].label == "Route"


def test_jadwal_route_change():
    at = AppTest.from_file("pages/2_Jadwal.py", default_timeout=30)
    at.run()
    assert not at.exception
    # Change route - should not crash
    if len(at.selectbox[0].options) > 1:
        at.selectbox[0].set_value(at.selectbox[0].options[1]).run()
        assert not at.exception


def test_prediksi_loads():
    at = AppTest.from_file("pages/3_Prediksi_Keterlambatan.py", default_timeout=10)
    at.run()
    assert not at.exception
    # Filters exist
    assert at.selectbox[0].label == "Route"
    # Checkbox should exist
    assert at.checkbox[0].label == "Urut Naik"


def test_prediksi_checkbox_bug():
    """Bug #1: checkbox must not self-reference its own key."""
    at = AppTest.from_file("pages/3_Prediksi_Keterlambatan.py", default_timeout=10)
    at.run()
    assert not at.exception
    # Toggle checkbox
    at.checkbox[0].set_value(True).run()
    assert not at.exception
    assert at.checkbox[0].value is True


def test_prediksi_status_filter():
    at = AppTest.from_file("pages/3_Prediksi_Keterlambatan.py", default_timeout=10)
    at.run()
    assert not at.exception
    # Filter by Cepat status
    at.selectbox[2].set_value("Cepat").run()
    assert not at.exception


def test_prediksi_query_params():
    """Verify query params are synced."""
    at = AppTest.from_file("pages/3_Prediksi_Keterlambatan.py", default_timeout=10)
    at.run()
    assert not at.exception
    qp = at.query_params
    assert "route" in qp
    assert "asc" in qp


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
