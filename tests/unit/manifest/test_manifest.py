from pathlib import Path

import pytest
from signetum.manifest import ManifestError, load_manifest

FIXTURE = Path(__file__).parents[3] / "tests/fixtures/portable-python" / "signetum.toml"


def test_load_manifest_preserves_language_neutral_repository_facts() -> None:
    manifest = load_manifest(FIXTURE)

    assert manifest.schema_version == 5
    assert manifest.signetum.protocol == 2
    assert manifest.repository.architecture == "docs/ARCHITECTURE.md"
    assert manifest.profiles.enabled == ("python-default@1", "git-worktrunk@1")
    assert manifest.impact.rules[0].shards == (
        "python:ruff",
        "python:format",
        "python:ty",
        "python:unit",
    )
    assert manifest.validation.shards[0].name == "python:sync"
    assert manifest.validation.shards[1].name == "repository:diff"
    assert manifest.validation.shards[1].requires == ()
    ruff = next(item for item in manifest.validation.shards if item.name == "python:ruff")
    assert ruff.requires == ("python:sync",)
    assert manifest.validation.gates[-1].name == "final"


@pytest.mark.parametrize(
    ("name", "text", "message"),
    [
        ("signetum.toml", "schema_version = 1\n", "unsupported manifest schema: 1"),
        ("repository.toml", "schema_version = 5\n", "must be named signetum.toml"),
        (
            "signetum.toml",
            """schema_version = 5
[delivery]
branch = "main"
[signetum]
protocol = 2
template_version = "main"
[repository]
architecture = "docs/ARCHITECTURE.md"
changes = "changes"
decisions = "docs/decisions"
""",
            "unknown dataclass fields",
        ),
        (
            "signetum.toml",
            """schema_version = 5
[delivery]
branch = "main"
[signetum]
protocol = 2
[profiles]
enabled = ["python-default@1", "python-default@1"]
[repository]
architecture = "docs/ARCHITECTURE.md"
changes = "changes"
decisions = "docs/decisions"
""",
            "profiles.enabled must contain unique identities",
        ),
    ],
)
def test_invalid_manifest_is_rejected(tmp_path: Path, name: str, text: str, message: str) -> None:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ManifestError, match=message):
        load_manifest(path)


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ('enabled = ["not-versioned"]', "profile identity must be immutable"),
        (
            'enabled = ["python-default@1"]\n'
            '[profiles.replacements]\n"python-default@1" = "python-default@1"',
            "a profile cannot replace itself",
        ),
    ],
)
def test_profile_composition_errors_fail_closed(tmp_path: Path, extra: str, message: str) -> None:
    path = tmp_path / "signetum.toml"
    path.write_text(
        f"""schema_version = 5
[delivery]
branch = "main"
[signetum]
protocol = 2
[profiles]
{extra}
[repository]
architecture = "docs/ARCHITECTURE.md"
changes = "changes"
decisions = "docs/decisions"
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match=message):
        load_manifest(path)


@pytest.mark.parametrize(
    ("rule", "message"),
    [
        ('name = "Invalid"\npaths = ["src/**"]', "impact rule name must be namespaced"),
        ('name = "valid.rule"\npaths = ["../outside"]', "impact path must be"),
        (
            'name = "same.rule"\npaths = ["src/**"]\n'
            '[[impact.rules]]\nname = "same.rule"\npaths = ["tests/**"]',
            "impact.rules names must be unique",
        ),
    ],
)
def test_impact_contract_rejects_ambiguous_or_escaping_rules(
    tmp_path: Path, rule: str, message: str
) -> None:
    path = tmp_path / "signetum.toml"
    path.write_text(
        f"""schema_version = 5
[delivery]
branch = "main"
[signetum]
protocol = 2
[repository]
architecture = "docs/ARCHITECTURE.md"
changes = "changes"
decisions = "docs/decisions"
[[impact.rules]]
{rule}
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match=message):
        load_manifest(path)


def test_missing_configuration_is_an_invocation_error(tmp_path: Path) -> None:
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "signetum.toml")


@pytest.mark.parametrize(
    ("validation", "message"),
    [
        ("shards = []\ngates = []", "unique named shards"),
        (
            '[[validation.shards]]\nname = "repo:one"\ncommand = ["git", "diff"]\n'
            '[[validation.gates]]\nname = "member"\nshards = ["repo:one"]',
            "member and final gates",
        ),
    ],
)
def test_validation_graph_is_strict_and_named(
    tmp_path: Path, validation: str, message: str
) -> None:
    path = tmp_path / "signetum.toml"
    path.write_text(
        f"""schema_version = 5
[delivery]
branch = "main"
[signetum]
protocol = 2
[repository]
architecture = "docs/ARCHITECTURE.md"
changes = "changes"
decisions = "docs/decisions"
[validation]
{validation}
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match=message):
        load_manifest(path)


_COVERAGE_GATES = (
    '[[validation.gates]]\nname = "member"\nshards = ["repo:member"]\n'
    '[[validation.gates]]\nname = "final"\nshards = ["repo:member"]\n'
)


def _coverage_manifest(tmp_path: Path, shards: str) -> Path:
    path = tmp_path / "signetum.toml"
    path.write_text(
        'schema_version = 5\n[delivery]\nbranch = "main"\n[signetum]\nprotocol = 2\n'
        '[repository]\narchitecture = "docs/ARCHITECTURE.md"\nchanges = "changes"\n'
        'decisions = "docs/decisions"\n[validation]\n' + shards + _COVERAGE_GATES,
        encoding="utf-8",
    )
    return path


def _shard(name: str, *, covers: tuple[str, ...] = (), world: bool = False) -> str:
    text = f'[[validation.shards]]\nname = "{name}"\ncommand = ["true"]\n'
    if covers:
        text += "covers = [" + ", ".join(f'"{item}"' for item in covers) + "]\n"
    if world:
        text += 'evidence = "world"\nfindings_command = ["true"]\n'
    return text


def test_a_shard_may_declare_the_shards_it_covers(tmp_path: Path) -> None:
    manifest = load_manifest(
        _coverage_manifest(
            tmp_path, _shard("repo:member") + _shard("repo:batch", covers=("repo:member",))
        )
    )
    batch = next(item for item in manifest.validation.shards if item.name == "repo:batch")
    assert batch.covers == ("repo:member",)


@pytest.mark.parametrize(
    ("shards", "message"),
    [
        (_shard("repo:member") + _shard("repo:batch", covers=("repo:absent",)), "undeclared"),
        (_shard("repo:member", covers=("repo:member",)), "itself"),
        (
            _shard("repo:member")
            + _shard("repo:outside", world=True)
            + _shard("repo:batch", covers=("repo:outside",)),
            "tree",
        ),
        (
            _shard("repo:member") + _shard("repo:outside", covers=("repo:member",), world=True),
            "tree",
        ),
        (
            _shard("repo:member", covers=("repo:batch",))
            + _shard("repo:batch", covers=("repo:member",)),
            "cycl",
        ),
    ],
)
def test_coverage_declarations_are_checked_at_load(
    tmp_path: Path, shards: str, message: str
) -> None:
    with pytest.raises(ManifestError, match=message):
        load_manifest(_coverage_manifest(tmp_path, shards))


@pytest.mark.parametrize(
    ("declaration", "accepted"),
    [
        (
            'command = ["run", "--priority", "{signetum.priority_nodes_file}", '
            '"--node-report", "{signetum.node_report_file}"]\n',
            True,
        ),
        (
            'command = ["run", "{signetum.base}", "{signetum.ratchet_baseline}", '
            '"{signetum.contribution_paths_file}", "{signetum.admission_base}", '
            '"{signetum.validation_workers}", "{signetum.recovery_report_file}"]\n',
            True,
        ),
        (
            'command = ["true"]\nratchet_command = ["measure", "{signetum.validation_workers}"]\n',
            True,
        ),
        ('command = ["true"]\nratchet_command = ["measure", "{signetum.base}"]\n', False),
        ('command = ["run", "{signetum.schedule_file}"]\n', False),
        ('command = ["run", "{signetum.unknown_file}"]\n', False),
        ('command = ["run", "--priority={signetum.priority_nodes_file}"]\n', False),
        (
            'command = ["true"]\nevidence = "world"\n'
            'findings_command = ["audit", "{signetum.node_report_file}"]\n',
            False,
        ),
    ],
)
def test_engine_placeholders_are_checked_at_load(
    tmp_path: Path, declaration: str, accepted: bool
) -> None:
    shards = _shard("repo:member") + '[[validation.shards]]\nname = "repo:other"\n' + declaration
    path = _coverage_manifest(tmp_path, shards)
    if accepted:
        load_manifest(path)
    else:
        with pytest.raises(ManifestError, match="placeholder"):
            load_manifest(path)


@pytest.mark.parametrize("listed", [True, False])
def test_a_schedule_file_is_a_declared_validation_input(tmp_path: Path, listed: bool) -> None:
    path = _coverage_manifest(
        tmp_path,
        'schedule_file = "weights.json"\n'
        + '[[validation.shards]]\nname = "repo:member"\n'
        + 'command = ["run", "{signetum.schedule_file}"]\n',
    )
    if listed:
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("[validation]", 'lockfiles = ["weights.json"]\n[validation]'))
        assert load_manifest(path).validation.schedule_file == "weights.json"
    else:
        with pytest.raises(ManifestError, match="lockfiles"):
            load_manifest(path)


def test_an_order_only_prerequisite_must_be_declared(tmp_path: Path) -> None:
    shards = _shard("repo:member") + (
        '[[validation.shards]]\nname = "repo:tests"\ncommand = ["true"]\nafter = ["repo:absent"]\n'
    )
    with pytest.raises(ManifestError, match="undeclared"):
        load_manifest(_coverage_manifest(tmp_path, shards))
