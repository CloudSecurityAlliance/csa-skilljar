import csa_skilljar


def test_version_is_a_release_shaped_string():
    """Asserted by SHAPE, not by literal. A hardcoded version makes every release a
    five-file edit, and an edit made only to turn a suite green teaches nothing. What
    actually matters is that the value is well-formed and single-sourced - the release
    workflow separately refuses to publish when the git tag disagrees with it."""
    import re
    assert re.fullmatch(r"\d+\.\d+\.\d+([-.][0-9A-Za-z.]+)?", csa_skilljar.__version__), (
        f"{csa_skilljar.__version__!r} is not a version the release tag check can match")


def test_the_installed_metadata_agrees_with_the_module():
    """The two can drift: __version__ is read by pyproject's dynamic version, so a stale
    editable install reports one number while the source says another."""
    from importlib.metadata import version
    installed = version("csa-skilljar")
    assert installed == csa_skilljar.__version__, (
        f"installed metadata says {installed}, the module says "
        f"{csa_skilljar.__version__}. After bumping the version, refresh the editable "
        f"install: .venv/bin/python -m pip install -e '.[dev]'. This matters because "
        f"`check_access` reports the module value while `pipx list` reports the "
        f"metadata one, and a user seeing two numbers cannot tell which is running.")


def test_typed_marker_is_present():
    from pathlib import Path
    marker = Path(csa_skilljar.__file__).parent / "py.typed"
    assert marker.exists(), (
        "PEP 561 marker missing - a typed library whose types do not reach consumers "
        "is a broken promise"
    )
