# FRICTION-004: The server has no login, and nothing says so where you look for one

**Status:** Open
**Date identified:** 2026-08-30
**Type:** Discoverability

## Description

After a clean install on Windows, the project's owner opened `/mcp`, selected
`csa-skilljar`, and looked for a way to sign in. There is none, and there never will be:
this server uses the OAuth `client_credentials` grant, where **the credential is the
identity**. There is no browser, no redirect URI, no consent screen and no token cache —
that is CLAUDE.md's architectural fact #5, and it is deliberate.

The friction is that the design is invisible at the one moment it is questioned. `/mcp`
shows a server that is connected and healthy, offers no login affordance, and says
nothing about why. Absence of a control is indistinguishable from a missing feature.

## Why this is worth logging rather than dismissing

The person who hit it **designed the credential model**, wrote the ADR, and had authored
the installer that morning. If the architecture is not recallable from inside the client
by its own author, it is not discoverable by a CSA staff member who has never read the
spec — and their conclusion will be "this is broken", not "this is client_credentials".

The neighbouring server makes it worse in the ordinary way that consistency does.
`csa-google-workspace` is installed on the same machines, is registered by the same
DesktopSetup run, and **does** have an `authenticate` tool that opens a browser. Two CSA
servers, one signs you in and one silently does not.

## Attention tax

Small per occurrence, but it lands on every new installer exactly once, at the point where
they are deciding whether the thing works. And it produces the wrong bug report — "no
login option" rather than "no credential configured", which are different problems with
different fixes.

## The second, larger half

Neither of the owner's two installs carries a credential at all:

| install | environment |
|---|---|
| macOS | `CSA_SKILLJAR_PROFILE=parity` |
| Windows | `CSA_SKILLJAR_PROFILE=parity` |

So the honest answer to "why can't I log in" is two facts, not one: there is no login by
design, **and** this install cannot reach Skilljar yet. The installer says the second in
its closing output — but that output scrolls past inside a DesktopSetup run that is also
installing Slack and 43 plugins, and it is not in the log, because `Write-Host` does not
go through `Write-CsaLog`.

## Candidate resolutions

Not yet chosen — this is logged before deciding, deliberately.

1. **Say it in the server instructions.** The MCP `instructions` block is shown to the
   model, not the user, so this helps a model answer "how do I log in" correctly but does
   nothing for someone reading `/mcp`.
2. **Say it in `check_access`.** Already the tool everything points at; it should state
   plainly that this server has no interactive login and never will. Cheap, and it is
   where a model will look. Note this tool currently carries the stale v1 claim recorded
   in `TODO.md`, so it needs an edit regardless.
3. **Have the installer leave the statement somewhere durable** rather than only in
   scrolling output — the registration itself, or a line the debug log captures.
4. **Do nothing but document it** in `README.md` under installation, on the grounds that
   the real fix is configuring a credential and the login question evaporates once tools
   start working.

Option 2 plus 4 is the cheap combination; 3 is the one that would have prevented this
instance.

## Related

- `CLAUDE.md` architectural fact #5 — why `client_credentials` and not `authorization_code`
- `TODO.md` — the two stale v1-credential messages, one of which is in `check_access`
- `WAITING-FOR-003` — live write verification, separate matter
