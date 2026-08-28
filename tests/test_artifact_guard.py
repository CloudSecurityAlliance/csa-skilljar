"""The release guard, exercised with deliberately bad archives.

It lived as a heredoc inside `release.yml` until 2026-08-28: it ran once per release,
nothing could test it, and its first real firing was a FALSE POSITIVE that blocked
v0.9.0 — the rule matched the substring "credential" against every filename, so
`_tools/credentials.py` looked like a credential file.

A guard nobody can exercise is a guard nobody knows the behaviour of. These build real
zip and tar archives and feed them to the real script.
"""
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import check_artifact as ca  # noqa: E402


def wheel(tmp_path, names):
    p = tmp_path / "pkg-1.0-py3-none-any.whl"
    with zipfile.ZipFile(p, "w") as z:
        for n in names:
            z.writestr(n, "x")
    return p


def sdist(tmp_path, names):
    p = tmp_path / "pkg-1.0.tar.gz"
    body = tmp_path / "body"
    body.write_text("x")
    with tarfile.open(p, "w:gz") as t:
        for n in names:
            t.add(body, arcname=n)
    return p


GOOD = ["csa_skilljar/__init__.py", "csa_skilljar/py.typed",
        "csa_skilljar/mcp/_tools/credentials.py"]


# --- the false positive that blocked a release ---------------------------------------

def test_a_module_named_credentials_is_not_a_credential(tmp_path):
    """THE regression. `credentials.py` is a module about credentials, not one
    containing any. The old rule matched the substring and refused a real release."""
    assert ca.check([wheel(tmp_path, GOOD)]) == []


@pytest.mark.parametrize("name", [
    "csa_skilljar/mcp/_tools/credentials.py",
    "csa_skilljar/auth.py",
    "tests/test_credentials.py",
    "csa_skilljar/secrets_helper.py",
    "docs/TOKEN-HANDLING.md",
])
def test_source_named_after_the_subject_ships(tmp_path, name):
    """Naming a file after the thing it handles must not make it unshippable, or the
    guard trains people to work around it."""
    assert ca.check([wheel(tmp_path, [name, "csa_skilljar/py.typed"])]) == []


# --- what it must still catch ---------------------------------------------------------

@pytest.mark.parametrize("bad", [
    ".env", "csa_skilljar/.env", ".env.local", "config/prod.env",
    "certs/server.pem", "certs/server.key", "keystore.jks",
    "id_rsa", "client_secret.json", "client_secrets.json",
    "credentials.json", "token.json", "service-account-prod.json",
    ".netrc", ".pypirc", "secrets.yaml",
])
def test_credential_shaped_files_are_refused(tmp_path, bad):
    problems = ca.check([wheel(tmp_path, [*GOOD, bad])])
    assert problems, f"{bad} shipped without complaint"
    assert bad in problems[0]


@pytest.mark.parametrize("bad", ["analysis/entity-inventory.csv",
                                 "docs-html/index.html",
                                 ".github/workflows/release.yml"])
def test_repository_furniture_is_refused(tmp_path, bad):
    assert ca.check([wheel(tmp_path, [*GOOD, bad])])


def test_the_sdist_prefix_does_not_hide_a_directory(tmp_path):
    """An sdist puts everything under `pkg-version/`, so a naive prefix check stops
    seeing `analysis/` at all — and the exclusion silently covers nothing."""
    problems = ca.check([sdist(tmp_path, ["pkg-1.0/csa_skilljar/py.typed",
                                          "pkg-1.0/analysis/inventory.csv"])])
    assert problems and "analysis/inventory.csv" in problems[0]


def test_a_missing_py_typed_is_refused(tmp_path):
    problems = ca.check([wheel(tmp_path, ["csa_skilljar/__init__.py"])])
    assert any("py.typed" in p for p in problems)


def test_an_empty_archive_is_refused(tmp_path):
    """Zero entries would otherwise pass every 'nothing bad is present' rule."""
    assert ca.check([wheel(tmp_path, [])])


def test_no_distributions_at_all_is_a_failure():
    """`dist/*.whl` unexpanded, or a build that produced nothing, must not read as
    'clean'. This is the shape that lets an empty release through."""
    assert ca.main(["definitely/not/here.whl"]) == 1


# --- the real artifact ----------------------------------------------------------------

def test_this_projects_own_distribution_passes_if_one_is_built():
    dist = Path(__file__).resolve().parent.parent / "dist"
    built = sorted(dist.glob("*.whl")) + sorted(dist.glob("*.tar.gz"))
    if not built:
        pytest.skip("no dist/ built; run `python -m build` to exercise this")
    assert ca.check(built) == []
