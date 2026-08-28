"""Environment -> Settings -> SkilljarClient.

Two design points, both easy to "fix" into bugs:

* **Nothing resolves eagerly.** Credentials are looked up on first tool use, not at
  startup. An MCP client reports a startup crash as an opaque "server failed to start",
  so failing fast here is a *silent* failure; deferring makes it a tool error the user
  reads in chat, with the remedy in it.
* **One client per thread.** mcp 2.x dispatches sync tool handlers through
  `anyio.to_thread.run_sync`, so concurrent calls land on different threads.
"""
from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass

from .. import exceptions as exc
from ..auth import V2Credentials
from ..backend import V2Backend
from ..client import SkilljarClient
from ..policy import Policy, PolicyBackend
from ..v1backend import V1Backend, V1Credentials

V2_ID_VAR = "CSA_SKILLJAR_V2_CLIENT_ID"
V2_SECRET_VAR = "CSA_SKILLJAR_V2_CLIENT_SECRET"      # nosec B105 # a variable name, not a secret
V1_KEY_VAR = "CSA_SKILLJAR_V1_API_KEY"
PROFILE_VAR = "CSA_SKILLJAR_PROFILE"

# Module constants, not f-strings built at call time. The startup-warning path must have
# no data dependency on the environment whatsoever - only a control-flow one - or CodeQL
# reports py/clear-text-logging-sensitive-data, since `os.environ` is a taint source and
# it does not distinguish "a value from env" from "a constant chosen because of env".
V2_MISSING_WARNING = (
    f"{V2_ID_VAR} / {V2_SECRET_VAR} not set - v2 tools will report setup steps. "
    f"Call `check_access` for details."
)
V1_MISSING_WARNING = (
    f"{V1_KEY_VAR} not set - the v1-only capabilities are unavailable. Learner progress "
    f"(lesson counts, credits, re-enrolment history) is v1-only; everything else works "
    f"without it. Call `check_access` for details."
)


@dataclass(frozen=True)
class Settings:
    v2_client_id: str | None = None
    v2_client_secret: str | None = None
    v1_api_key: str | None = None
    profile: str = "parity"
    base_url: str = "https://api.skilljar.com"

    def __repr__(self) -> str:      # never let a credential reach a log line
        return (f"Settings(v2_client_id={'set' if self.v2_client_id else 'unset'}, "
                f"v2_client_secret={'set' if self.v2_client_secret else 'unset'}, "
                f"v1_api_key={'set' if self.v1_api_key else 'unset'}, "
                f"profile={self.profile!r})")


def settings_from_env(env: Mapping[str, str]) -> Settings:
    return Settings(
        v2_client_id=env.get(V2_ID_VAR) or None,
        v2_client_secret=env.get(V2_SECRET_VAR) or None,
        v1_api_key=env.get(V1_KEY_VAR) or None,
        profile=env.get(PROFILE_VAR) or "parity",
    )


def presence_from_env(env: Mapping[str, str]) -> CredentialPresence:
    """Which credentials are present, computed from the environment's KEYS.

    Deliberately does not read any value, and deliberately does not go through
    `Settings`. The startup-warning path therefore has no data dependency on a secret
    at all - not the value, not a boolean derived from it. This is what finally
    satisfied CodeQL's `py/clear-text-logging-sensitive-data`, and it is also simply
    the more honest expression of the question being asked: *is the variable set?*
    """
    def _set(name: str) -> bool:
        value = env.get(name)
        return value is not None and value.strip() != ""

    return CredentialPresence(
        v2=_set(V2_ID_VAR) and _set(V2_SECRET_VAR),
        v1=_set(V1_KEY_VAR),
    )


@dataclass(frozen=True)
class CredentialPresence:
    """Which credentials are configured - and nothing else.

    Exists so the startup-warning path never receives an object that holds a secret.
    CodeQL flagged `py/clear-text-logging-sensitive-data` on the original design, where
    `Settings` flowed into `startup_warnings()` and its output was printed. No value was
    ever printed - the messages are built from constants - but nothing *structurally*
    prevented a later edit from interpolating one. Narrowing the input makes "a startup
    warning cannot contain a credential" a property of the types rather than of careful
    coding, which is a better answer than an inline suppression.
    """

    v2: bool
    v1: bool


def startup_warnings(presence: CredentialPresence) -> list[str]:
    """Tier 1: synchronous, zero network. Written to stderr by the CLI.

    Takes only booleans by design - see `CredentialPresence`.

    Tier 2 - actually validating the credential - happens in the background after
    `initialize` returns, because a blocking network call here turns a slow Skilljar
    into an opaque "server failed to start".
    """
    out: list[str] = []
    if not presence.v2:
        out.append(V2_MISSING_WARNING)
    if not presence.v1:
        out.append(V1_MISSING_WARNING)
    return out


class ClientProvider:
    """Callable returning a thread-local `SkilljarClient`. Resolves credentials lazily."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings; self._local = threading.local()

    def __call__(self) -> SkilljarClient:
        existing = getattr(self._local, "client", None)
        if existing is not None:
            return existing
        s = self._settings
        if not (s.v2_client_id and s.v2_client_secret):
            raise exc.CredentialsMissing(
                f"v2 credentials are not configured, so this tool cannot run. Set "
                f"{V2_ID_VAR} and {V2_SECRET_VAR} in your MCP client configuration and "
                f"restart the server. Obtain a v2 API client from the Skilljar Dashboard. "
                f"Call `check_access` to see what is currently available.")
        policy = Policy.from_profile(s.profile)
        creds = V2Credentials(s.v2_client_id, s.v2_client_secret, base_url=s.base_url)
        backend = PolicyBackend(V2Backend(creds, base_url=s.base_url), policy)
        # The v1 backend is OPTIONAL and policy-wrapped with the SAME policy: one gate
        # table covers both APIs, so a capability cannot be gated in one and open in the
        # other. Absent, the v1-only tools raise a typed error naming the variable to
        # set - a v1 key is not needed for any of the v2 surface.
        v1 = None
        if s.v1_api_key:
            v1 = PolicyBackend(
                V1Backend(V1Credentials(s.v1_api_key), base_url=s.base_url), policy)
        client = SkilljarClient(backend, v1=v1)
        self._local.client = client
        return client
