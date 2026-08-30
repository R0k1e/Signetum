import pytest

from reposeal.profiles import (
    ProfileDeclaration,
    ProfileError,
    resolve_profiles,
)


def test_selected_profiles_activate_only_explicit_dependencies() -> None:
    profiles = resolve_profiles(("python-uv@1", "git-worktrunk@1"))

    assert tuple(profile.identity for profile in profiles) == (
        "shared-core@1",
        "python-uv@1",
        "git-worktrunk@1",
    )


def test_unsupported_profile_is_rejected() -> None:
    with pytest.raises(ProfileError, match="unsupported profile: node-npm@1"):
        resolve_profiles(("node-npm@1",))


def test_undeclared_dependency_is_rejected() -> None:
    catalog = {
        "broken-test-profile@1": ProfileDeclaration(
            identity="broken-test-profile@1",
            authorities=("test",),
            requires=("missing@1",),
        )
    }
    with pytest.raises(ProfileError, match="undeclared profile dependency"):
        resolve_profiles(("broken-test-profile@1",), catalog=catalog)


def test_duplicate_authority_is_rejected() -> None:
    catalog = {
        "python-uv@1": ProfileDeclaration(
            identity="python-uv@1", authorities=("python-environment",)
        ),
        "python-other-test@1": ProfileDeclaration(
            identity="python-other-test@1", authorities=("python-environment",)
        ),
    }
    with pytest.raises(ProfileError, match="duplicate authority: python-environment"):
        resolve_profiles(("python-uv@1", "python-other-test@1"), catalog=catalog)
