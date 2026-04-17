from agentguard.security.scanner import Severity, get_rules


def test_every_critical_rule_has_atlas_tag() -> None:
    missing = [
        rule.rule_id
        for rule in get_rules()
        if rule.severity == Severity.CRITICAL and not rule.mitre_atlas
    ]
    assert not missing, f"CRITICAL rules missing MITRE ATLAS mapping: {missing}"


def test_every_rule_has_ast10_tag() -> None:
    missing = [rule.rule_id for rule in get_rules() if not rule.owasp_ast10]
    assert not missing, f"Rules missing OWASP AST10 mapping: {missing}"
