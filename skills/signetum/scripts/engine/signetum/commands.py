"""The sole public command registry, shared by direct and installed execution."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    path: tuple[str, ...]
    module: str
    function: str = "main"
    prefix: tuple[str, ...] = ()
    suffix: tuple[str, ...] = ()
    help: str = ""
    panel: str = "Development"
    passthrough: bool = True


BOOTSTRAP = {
    "setup": "Prepare this installed Skill's isolated environment.",
    "identity": "Show complete Skill and engine identities.",
    "update": "Install the latest stable Skill. --check and --to stay optional; other commands stay offline.",
}


LIFECYCLE = (
    "workspace-open",
    "changed",
    "ready",
    "batch-open",
    "batch-admit",
    "batch-continue",
    "final",
    "batch-deliver",
)
CHANGE = ("current", "history", "record", "resolve", "retract", "reconcile", "retire")
COMMANDS = (
    *(
        Command((name,), "lifecycle", prefix=(name,), help=f"Run {name}.", panel="Delivery")
        for name in LIFECYCLE
    ),
    Command(
        ("status",), "change_cli", "main", ("status",), help="Show state, blockers and next action."
    ),
    Command(("change", "open"), "change_open", help="Draft one change."),
    Command(
        ("change", "view"),
        "change_record",
        suffix=("--review",),
        help="Review outcomes and approval.",
    ),
    *(
        Command(
            ("change", name),
            "change_cli",
            "main",
            (name,),
            help=f"{name.capitalize()} development records.",
        )
        for name in CHANGE
    ),
    Command(("test", "run"), "test_diagnostic", help="Run bounded feedback without readiness."),
    Command(
        ("test", "schedule"), "pytest_scheduling", help="Inspect optional weighted scheduling."
    ),
    Command(
        ("test", "partition"), "ci_partitions", help="Plan, run or combine exact CI partitions."
    ),
    *(
        Command(
            ("adopt", name),
            "adoption",
            prefix=(name,),
            help=f"{name.capitalize()} reviewed project bindings.",
            panel="Setup and maintenance",
        )
        for name in ("inspect", "preview", "apply")
    ),
    Command(
        ("adopt", "runner"),
        "profiles.existing_runner",
        help="Propose existing project runner bindings.",
        panel="Setup and maintenance",
    ),
    Command(
        ("maintenance",),
        "maintenance",
        help="Prepare, synchronize or clean workspaces.",
        panel="Setup and maintenance",
    ),
    Command(
        ("check", "manifest"),
        "check_cli",
        "check_manifest",
        help="Validate project configuration.",
        passthrough=False,
    ),
    Command(
        ("check", "traceability"),
        "check_cli",
        "check_traceability",
        help="Inspect change and decision relations.",
        passthrough=False,
    ),
)
