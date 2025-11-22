def test_import():
    # 这里的 placeholder_name 会被 init_repo 脚本自动替换为真实的包名
    import placeholder_name
    assert placeholder_name is not None