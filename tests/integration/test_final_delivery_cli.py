"""Final and publication compose through the same explicit public CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from operation_messages import operation_messages, write_operation_message
from signetum import lifecycle
from test_batch_admission import _git
from test_delivery_discoveries import member_and_batch


def _cli(repository, *arguments):
    return subprocess.run(  # noqa: S603 -- public CLI in an owned disposable repository
        [sys.executable, "-m", "signetum.cli", *arguments],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("combined", [False, True])
def test_final_and_delivery_publish_the_same_qualified_tree(tmp_path, combined):
    member, batch = member_and_batch(tmp_path)
    target = tmp_path / "repository"
    lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,), messages=operation_messages(1))
    tip = _git(batch, "rev-parse", "HEAD")
    base = _git(target, "rev-parse", "HEAD")
    message = write_operation_message(
        tmp_path, name="publication.txt", text="Merge the qualified batch.\n"
    )
    if combined:
        command = (
            "final",
            "--deliver",
            "--target",
            str(target),
            "--actor",
            "Repository owner",
            "--source",
            "Explicit fixture delivery authorization",
            "--message-file",
            str(message),
        )
    else:
        final = _cli(batch, "final")
        assert final.returncode == 0, final.stdout + final.stderr
        command = (
            "batch-deliver",
            str(batch),
            str(target),
            base,
            tip,
            "--message-file",
            str(message),
        )
    delivered = _cli(batch, *command)
    assert delivered.returncode == 0, delivered.stdout + delivered.stderr
    result = json.loads(delivered.stdout)
    assert result["outcome"] == "delivered"
    assert result["cleanup"]["status"] == "pending"
    landed = _git(target, "rev-parse", "HEAD")
    assert _git(target, "rev-parse", f"{landed}^{{tree}}") == _git(
        batch, "rev-parse", f"{tip}^{{tree}}"
    )
    assert _git(target, "show", "-s", "--format=%P", landed).split() == [base, tip]
    assert batch.is_dir() and member.is_dir()
    if combined:
        receipt = json.loads(Path(result["validation"]["final_receipt"]).read_text())
        assert receipt["delivery_authorization"]["actor"] == "Repository owner"


def test_combined_delivery_requires_explicit_authorization_before_checks(tmp_path):
    _member, batch = member_and_batch(tmp_path)
    target = tmp_path / "repository"
    base = _git(target, "rev-parse", "HEAD")
    result = _cli(batch, "final", "--deliver", "--target", str(target))
    assert result.returncode != 0
    assert not list(lifecycle._receipt_root(batch).glob("final-*.json"))
    assert _git(target, "rev-parse", "HEAD") == base


def test_failed_final_does_not_publish(tmp_path):
    member, batch = member_and_batch(tmp_path)
    target = tmp_path / "repository"
    manifest = member / "signetum.toml"
    failure = tmp_path / "fail-final"
    command = [
        sys.executable,
        "-c",
        f"from pathlib import Path; import sys; sys.exit(int(Path({str(failure)!r}).exists()))",
    ]
    manifest.write_text(
        manifest.read_text().replace('command = ["true"]', "command = " + json.dumps(command))
    )
    _git(member, "add", "signetum.toml")
    _git(member, "commit", "-m", "declare failing final")
    lifecycle.validate(member, "member")
    lifecycle.admit(batch, (member,), messages=operation_messages(1))
    failure.touch()
    base = _git(target, "rev-parse", "HEAD")
    result = _cli(
        batch,
        "final",
        "--deliver",
        "--target",
        str(target),
        "--actor",
        "Repository owner",
        "--source",
        "Explicit fixture authorization",
    )
    assert result.returncode != 0
    assert _git(target, "rev-parse", "HEAD") == base
