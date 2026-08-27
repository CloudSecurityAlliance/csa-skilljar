"""Does the package actually install and run?

Every other test imports from the working tree, where `mcp` happens to be present
because it is a dev dependency. That cannot see the bug this file exists for:
`mcp` was an optional extra while the console script imported it unconditionally, so
`pipx install csa-skilljar` put a command on PATH that crashed with ModuleNotFoundError.

Found by installing it for real. Nothing short of installing it for real would have.
"""
from __future__ import annotations

import ast
import pathlib
import subprocess
import sys

import pytest

import csa_skilljar

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _runtime_dependencies() -> list[str]:
    """The package's declared runtime dependencies, excluding extras.

    Read from installed metadata rather than parsing pyproject.toml: `tomllib` is
    stdlib only from 3.11 and this project's floor is 3.10, which the CI matrix caught
    immediately. Metadata is also the better source - it is what actually got built and
    installed, not what the source file intended.
    """
    from importlib.metadata import requires
    return [r for r in (requires("csa-skilljar") or []) if "extra ==" not in r]


def test_mcp_is_a_required_dependency_not_an_extra():
    """The console script is installed unconditionally, so its imports must be too."""
    deps = " ".join(_runtime_dependencies())
    assert "mcp" in deps, (
        "csa-skilljar-mcp imports mcp at module scope. If mcp is optional, a plain "
        "`pip install csa-skilljar` puts a broken command on PATH."
    )


def test_every_module_the_package_imports_is_a_runtime_dependency():
    """Walks the real import graph rather than trusting a list.

    Uses `ast`, not line matching: the first version matched a line of prose inside the
    server's INSTRUCTIONS string that began "from here. If an operation is refused..."
    and reported it as an undeclared dependency. A guard with false positives gets
    muted, and a muted guard is worse than none (ZD-2).
    """
    declared = {d.split(">")[0].split("=")[0].split("[")[0].split(";")[0].strip().replace("-", "_")
                for d in _runtime_dependencies()}
    declared |= {"csa_skilljar"}
    stdlib = set(sys.stdlib_module_names)
    offenders: list[str] = []
    for path in (ROOT / "src" / "csa_skilljar").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:                      # relative import, always ours
                    continue
                mods = [(node.module or "").split(".")[0]]
            else:
                continue
            for mod in mods:
                if mod and mod not in stdlib and mod not in declared and mod != "__future__":
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} imports {mod}")
    assert not offenders, (
        "modules imported by the package but not declared as runtime dependencies:\n  "
        + "\n  ".join(sorted(offenders))
    )


@pytest.mark.skipif("not config.getoption('--install-test', default=False)",
                    reason="builds a wheel and installs it; run with --install-test")
def test_a_built_wheel_installs_and_the_console_script_runs(tmp_path):
    """The conclusive version. Builds a wheel, installs it into a clean venv with no
    dev dependencies, and runs the console script. This is what CI runs on every PR."""
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
                   cwd=ROOT, check=True, capture_output=True)
    wheel = next(tmp_path.glob("*.whl"))
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = venv / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    subprocess.run([str(py), "-m", "pip", "install", "-q", str(wheel)], check=True)
    script = venv / ("Scripts" if sys.platform == "win32" else "bin") / "csa-skilljar-mcp"
    done = subprocess.run([str(script), "--version"], capture_output=True, text=True)
    assert done.returncode == 0, f"console script failed: {done.stderr}"
    assert csa_skilljar.__version__ in done.stderr


def test_the_integration_gate_skips_for_the_right_reason():
    """A skip count of zero means the gate leaked and those tests ran against a real
    learner database. But counting skips is not enough: without credentials the
    `live_client` fixture skips for its OWN reason, which masks a broken gate on any
    machine that has no credentials - and hides nothing on the machine that does.

    So assert the REASON. The first version of this test asserted only the count and
    could not fail when the gate was deliberately disabled.
    """
    import os
    import subprocess

    env = {k: v for k, v in os.environ.items() if k != "CSA_SKILLJAR_INTEGRATION"}
    # Credentials present or not, the gate must be what stops these running.
    env.setdefault("CSA_SKILLJAR_V2_CLIENT_ID", "probe-id")
    env.setdefault("CSA_SKILLJAR_V2_CLIENT_SECRET", "probe-secret")   # nosec B105 - fake
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rs", "tests/integration/", "--no-header"],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )
    assert done.returncode == 0, done.stdout
    assert " passed" not in done.stdout, (
        "integration tests RAN without CSA_SKILLJAR_INTEGRATION=1 - the gate leaked"
    )
    assert "CSA_SKILLJAR_INTEGRATION=1" in done.stdout, (
        "integration tests were skipped, but NOT by the integration gate. Something "
        "else stopped them, so the gate itself is unproven:\n" + done.stdout
    )
