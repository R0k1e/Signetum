from application import greeting


def test_greeting_uses_the_supplied_name() -> None:
    assert greeting("RepoSeal") == "Hello, RepoSeal!"
