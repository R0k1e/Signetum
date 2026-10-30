from application import greeting  # ty: ignore[unresolved-import]


def test_application_public_boundary() -> None:
    assert greeting("world") == "Hello, world!"
