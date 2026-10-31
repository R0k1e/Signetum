"""Delivery policy is explicit and shares the project manifest authority."""

import pytest
from signetum.policy import delivery_policy


@pytest.mark.parametrize("branch", ["main", "release/v1", "bad..branch", ""])
def test_delivery_branch_uses_manifest_not_entrypoint_policy(local_repository, branch):
    root, _ = local_repository
    path = root / "signetum.toml"
    path.write_text(path.read_text().replace('branch = "main"', f'branch = "{branch}"'))
    policy = root / ".agents/signetum/repo.yaml"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text("delivery: {branch: ignored}\n")
    if branch and ".." not in branch:
        assert delivery_policy(root).branch == branch
    else:
        with pytest.raises(ValueError):
            delivery_policy(root)
