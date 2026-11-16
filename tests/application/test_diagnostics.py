from petcam.application.diagnostics import collect, create_support_bundle


def test_diagnostics_use_injected_infrastructure_adapters():
    assert collect(lambda: {"state": "healthy"}) == {"state": "healthy"}
    assert create_support_bundle(
        lambda **kwargs: (kwargs["performance"] or {}).get("capture_status"),
        performance={"capture_status": {"active": True}},
    ) == {"active": True}
