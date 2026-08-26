import csa_skilljar


def test_version_is_single_sourced():
    assert csa_skilljar.__version__ == "0.0.1"


def test_typed_marker_is_present():
    from pathlib import Path
    marker = Path(csa_skilljar.__file__).parent / "py.typed"
    assert marker.exists(), (
        "PEP 561 marker missing - a typed library whose types do not reach consumers "
        "is a broken promise"
    )
