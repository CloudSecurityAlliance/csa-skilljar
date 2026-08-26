# Releasing

Publishing is automated via **PyPI Trusted Publishing (OIDC)**. Never `twine upload` by
hand, and never publish from a developer machine — the point of the whole chain is that
the released artifact's provenance is answerable without trusting anyone's laptop.

## The causal chain

```
PR → protected main → tag → CI build → attested OIDC publish
```

Each link is only as strong as the one before it. Branch protection on `main` is what
makes the rest mean anything: if someone can push straight to `main`, every downstream
guarantee is bypassed at the weakest point.

## Cutting a release

1. **Bump the version** in `src/csa_skilljar/__init__.py` — the single source of truth;
   `pyproject.toml` reads it dynamically. Add a dated `CHANGELOG.md` entry. Both go
   through the normal **branch + PR**, merged to `main` first.
2. **Check upstream has not moved** — `.venv/bin/python scripts/check_upstream.py`. A
   release that ships a coverage map contradicted by live Skilljar is worse than a late
   one.
3. **Run the live suite** if you have v2 credentials:
   `CSA_SKILLJAR_INTEGRATION=1 .venv/bin/python -m pytest tests/integration/`
4. **Create the release:** `gh release create vX.Y.Z --title "..." --notes "..."`.
   Publishing the GitHub Release triggers `.github/workflows/release.yml`.
5. **Approve the deployment.** The publish job runs in the protected `pypi` environment
   and pauses for a required reviewer before anything is uploaded.
6. **Verify it landed:** `pip install csa-skilljar==X.Y.Z` in a clean venv, then
   `csa-skilljar-mcp --version`. Confirm on PyPI that the published files carry build
   provenance — *"it's on by default"* is not verification.

## What the release workflow enforces

Everything below fails the release rather than warning:

- the full test suite, `pip-audit`, and `bandit` — a CVE disclosed since the last merge
  would otherwise ship
- **tag == packaged version**, compared explicitly. The tag is the provenance anchor:
  `git checkout vX.Y.Z` must reproduce exactly what shipped
- **artifact contents guard** — refuses to publish if anything credential-shaped, or
  `analysis/` or `docs-html/`, reached the sdist or wheel, and refuses if `py.typed` is
  *missing* (a typed library whose types do not reach consumers is a broken promise)

## One-time setup

1. On PyPI, add a **Trusted Publisher** for this project: owner
   `CloudSecurityAlliance`, repository `csa-skilljar`, workflow `release.yml`,
   environment `pypi`.
2. In GitHub → Settings → Environments, create `pypi` with a **required reviewer**.
   Scope any branch/tag policy to the release **tags**, not `main` — for a
   tag-triggered release the deploy ref is the tag, and a `main`-scoped rule blocks
   the publish.

No API token is ever created, so there is none to leak or rotate.

## Invariants

- **The tag must equal the version.** Enforced in CI, stated here because the failure is
  confusing if you meet it cold.
- **A PyPI version is permanent.** It can be yanked, never re-uploaded. Fix forward; never
  "re-release" the same number. This is why the tests and security scans run *before* the
  upload rather than after.
- **The README shown on PyPI is frozen at that release.** A documentation fix only reaches
  the package page on the next version bump — plan a patch release if a published page is
  wrong.
- **Pre-1.0, only the latest release is supported.** No backports.
