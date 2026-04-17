from reagent.attestation import BehavioralFingerprint, IQRDivergenceDetector


def _attested() -> BehavioralFingerprint:
    return BehavioralFingerprint(
        tool_calls=["Read:path", "Write:file_path"],
        egress_hosts=["api.anthropic.com"],
        file_writes=["src/*.py"],
        hook_subprocess=["git"],
        token_profile={
            "input_mean": 100.0,
            "input_std": 5.0,
            "output_mean": 50.0,
            "output_std": 2.0,
            "input_count": 10.0,
            "output_count": 10.0,
        },
    )


def test_iqr_flags_egress_outlier() -> None:
    attested = _attested()
    live = BehavioralFingerprint(
        tool_calls=["Read:path", "Write:file_path", "WebFetch:url"],
        egress_hosts=["api.anthropic.com", "evil.example.com"],
        file_writes=["src/*.py"],
        hook_subprocess=["git"],
        token_profile=attested.token_profile,
    )
    findings = IQRDivergenceDetector().check(attested, live, "deadbeef" * 8)
    dims = {f.dimension for f in findings}
    assert "egress_hosts" in dims
    egress_finding = next(f for f in findings if f.dimension == "egress_hosts")
    assert "evil.example.com" in egress_finding.observed
    assert "AML.T0024" in egress_finding.mitre_atlas


def test_iqr_does_not_flag_within_baseline() -> None:
    attested = _attested()
    live = attested.model_copy(deep=True)
    findings = IQRDivergenceDetector().check(attested, live, "deadbeef" * 8)
    assert findings == []
