# Backup resources

**Short on purpose.** Exposure, credential custody and accepted risks are already covered
properly in [`SECURITY-RESOURCES.md`](SECURITY-RESOURCES.md), and what this project never stores
is in [`DATA-RESOURCES.md`](DATA-RESOURCES.md). Restating either here would create a second place
recording the same thing, which is how two documents come to disagree without either saying it
lost. This file answers only the backup question, and then records the two things neither of the
others covers.

## The backup answer, measured

**There is nothing to back up.**

| | |
|---|---|
| Repository | Source and docs. Git is the recovery story; GitHub plus every clone is the copy |
| Credentials in the tree | **None.** All tracked files scanned for `GOCSPX-`, PEM private-key headers, AWS key shapes and `client_secret` with a value. One hit: `sk-live-DEADBEEF-do-not-print` in `tests/e2e/test_launcher.py` — a fixture that names its own purpose |
| Runtime state | **None.** 37 source files, measured: zero `open(..., "w")`, zero `write_text`, zero `Path.home()` writes. The server persists nothing, anywhere |
| Credentials at runtime | Environment variables held by whoever launches the process — `CSA_SKILLJAR_V1_API_KEY`, `CSA_SKILLJAR_V2_CLIENT_ID`, `CSA_SKILLJAR_V2_CLIENT_SECRET` |

Lose this repository: re-clone. Lose a laptop: nothing of this server's is lost, because it
keeps nothing. No snapshot, no retention policy, no restore drill — and inventing one would be
ceremony.

## 1. We publish our own unremediated findings, and the reason that is safe has a condition

`docs/security-audits/2026-08-30-defending-code-reference-harness-claude/` carries `FINDINGS.md`,
`ISSUES.md` and `THREAT_MODEL.md` in a **public** repo, and roughly ten of those findings are
still **open issues** here — T1, T22, T24/T26, T25/T34, T27, T30, T31/T29, T32/T37, T33.

That is a deliberate position and a defensible one, but it rests entirely on the deployment
shape that [`SECURITY-RESOURCES.md`](SECURITY-RESOURCES.md)'s exposure inventory records:
*"stdin/stdout only; no socket"*, and **"Cloudflare is not applicable to any row — there is no
inbound surface."** With no listener and the credential held by the operator who launched the
process, an attacker who does not already hold that credential gains nothing from knowing which
of our own assertions is missing. Most of the open findings are of that kind — *"three tests that
cannot fail"*, *"no `PROFILES` matrix"* — rather than reachable holes.

**The condition: that defence expires the moment this is anything other than a local stdio
server.** If it ever gains a network transport or is hosted, the open-findings list stops being
transparency and becomes a target list — and the audit directory needs revisiting *before* the
transport changes, not after. Recorded here because the exposure inventory states the fact and
nothing states what depends on it.

## 2. Where the credential actually lands today is another repo's behaviour

[`README.md`](README.md) explains why this server ships no credential, and
[`SECURITY-RESOURCES.md`](SECURITY-RESOURCES.md) covers custody of the one it is given. Neither
can describe what happens *before* that, because it happens in the installer.

The CSA setup script's fallback arm **inlines the API key and client secret into
`claude_desktop_config.json`**, and the `os.chmod(0o600)` meant to narrow that file **does
nothing on Windows**, where `os.chmod` honours only the read-only bit. So the credential whose
shape this repo is most careful about — `client_credentials`, where the secret *is* the
organisation's identity, with no per-person layer, no expiry and **no per-person revocation** —
currently has copies in a config file nobody is tracking.

That is CSA-Plugins#132, and `CSA_SKILLJAR_ENV_FILE` is the mechanism that closes it: a
credential in a file the installer places, rather than one pasted into a config. It is the one
item in the fleet with a live cost rather than a latent one, and it is invisible from inside this
repo, which is the reason to name it from inside this repo.

## Elsewhere

- Exposure surface, prompt injection, credential custody, accepted risks:
  [`SECURITY-RESOURCES.md`](SECURITY-RESOURCES.md).
- What this handles and never stores: [`DATA-RESOURCES.md`](DATA-RESOURCES.md).
- Distribution and rotation of the shared CSA clients: CSA-Plugins
  [`BACKUP-RESOURCES.md`](https://github.com/CloudSecurityAlliance-Internal/CSA-Plugins/blob/main/BACKUP-RESOURCES.md) —
  the repo that deliberately *does* keep secrets in git.
- `os.chmod` on Windows, and the other calls that run and lie:
  [`POSIX-AND-WINDOWS.md`](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/blob/main/POSIX-AND-WINDOWS.md).
