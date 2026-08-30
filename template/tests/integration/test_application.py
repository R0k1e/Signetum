from application import greeting


def test_application_public_boundary() -> None:
    assert greeting("world") == "Hello, world!"
