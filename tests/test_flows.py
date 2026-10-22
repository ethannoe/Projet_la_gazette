import pytest


def test_le_flow_prefect_se_charge():
    pytest.importorskip("prefect")
    from gazette.flows import collecte, planifier

    assert collecte.name == "collecte"
    assert callable(planifier)
