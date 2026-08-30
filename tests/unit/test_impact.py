from reposeal.impact import select_impact
from reposeal.manifest import ImpactRule


def test_multiple_language_rules_compose_as_one_deterministic_selection() -> None:
    rules = (
        ImpactRule(
            name="python.source",
            paths=("backend/**",),
            profiles=("python-default@1",),
            gates=("python.type", "python.unit"),
            shards=("python.unit",),
        ),
        ImpactRule(
            name="typescript.source",
            paths=("frontend/**",),
            profiles=("typescript-default@1",),
            gates=("typescript.type", "typescript.unit"),
            shards=("typescript.unit",),
            requires_final=True,
        ),
    )

    selection = select_impact(("backend/api.py", "frontend/view.ts", "README.md"), rules)

    assert selection.rules == ("python.source", "typescript.source")
    assert selection.profiles == ("python-default@1", "typescript-default@1")
    assert selection.gates == (
        "python.type",
        "python.unit",
        "typescript.type",
        "typescript.unit",
    )
    assert selection.unexplained == ("README.md",)
    assert selection.requires_final is True


def test_empty_diff_does_not_invent_validation() -> None:
    assert select_impact((), ()).requires_final is False
