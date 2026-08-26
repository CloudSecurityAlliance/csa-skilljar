# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Block 1 — a working server.** A local stdio MCP server over Skilljar's v2 API with four
  tools: `check_access` (which credentials work and what each unlocks),
  `describe_capabilities` (what exists but is not enabled), `report_a_problem` (a filable
  report carrying no ids and no credentials) and `list_courses` (one real read).
- `SkilljarClient` library with a `Backend` protocol seam, `V2Backend`, `FakeBackend`, and a
  conformance guard comparing all implementations signature-for-signature.
- Fail-closed `PolicyBackend`: a backend method with no declared gate is refused, not
  delegated. Named profiles (`parity` default, through `full`).
- OAuth `client_credentials` authentication with a local scope pre-check — an impossible call
  is refused by name, with no network traffic, using a scope table generated from the v2
  OpenAPI spec.
- `scripts/verify.sh`, `scripts/check_docs.py` (25 documentation claims asserted against the
  artifacts) and `scripts/gen_scopes.py`.
- Design spec: `docs/superpowers/specs/2026-08-26-csa-skilljar-design.md`.
- Upstream API snapshots in `specs/` — Skilljar v1 (OpenAPI 3.0.3) and v2 (OpenAPI 3.1.0),
  fetched 2026-08-26.
- Surface analysis in `analysis/` — a 66-entity reconciliation of both APIs, plus the
  live OAuth scope catalog.

119 tests, 96% coverage, offline with no network and no credentials.
