# RACI

Authority by decision domain. This is a solo, AI-assisted project inside CINO; the matrix exists
to make the boundaries explicit rather than to coordinate a team.

| Decision domain | Responsible | Accountable | Consulted | Informed |
|---|---|---|---|---|
| Project scope and phasing | Claude (proposes) | Kurt Seifried | CINO-Platform-Engineering patterns | CINO Project Tracker |
| Architecture and technical design | Claude (proposes) | Kurt Seifried | csa-google-workspace precedent | — |
| Security posture and threat model | Claude (drafts) | Kurt Seifried | CSA security practice | — |
| Credential issuance and scoping | Kurt Seifried | Kurt Seifried | — | — |
| What ships publicly | Claude (drafts) | Kurt Seifried | — | CSA |
| Release / publishing to PyPI | CI (Trusted Publishing) | Kurt Seifried | — | — |
| Retiring a v1 family once v2 ships it | Claude (proposes) | Kurt Seifried | `check_upstream.py` output | — |
| Public statements about Skilljar | Claude (drafts) | Kurt Seifried | — | CSA comms if it escalates |

## Notes

- **Credential issuance is not delegated.** Claude never creates, requests, or rotates a Skilljar
  credential. Anything that mints or changes a credential is Kurt's, which is also why Phase 2
  (credential administration tools) sits behind an off-by-default profile.
- **Anything outward-facing gets explicit approval** — creating public repos, publishing packages,
  or filing issues against a vendor. Accumulated approval does not transfer between actions.
- **Decision method is recorded per ADR**, using the CINO autonomy taxonomy, so the balance of
  authority over time is visible rather than assumed.
