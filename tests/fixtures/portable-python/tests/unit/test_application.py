from application import greeting  # ty: ignore[unresolved-import]


def test_greeting_uses_the_supplied_name() -> None:
    assert greeting("Signetum") == "Hello, Signetum!"
