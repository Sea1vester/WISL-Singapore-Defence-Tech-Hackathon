from __future__ import annotations

import logging

from ..base import ParsedLogEntry

logger = logging.getLogger(__name__)


class OrcristSink:
    """Reference stub for the planned Orcrist integration.

    Orcrist (https://orcrist.org) is an external data-fusion vendor the team will work
    with directly. No API contract, endpoint, or auth scheme has been confirmed yet, so
    this sink deliberately sends no data anywhere until it's implemented.

    NOTE: WISL's own design (Pillar 1) commits to a sovereign, self-hosted pipeline so
    that operational telemetry never passes through third-party commercial APIs. Before
    enabling this sink against real flight-log data, confirm with the team whether
    routing that data through Orcrist is compatible with that requirement.

    To finish this integration once Orcrist provides technical details: set `endpoint`
    and `api_key`, implement the request in `write()`, and flip `enabled=True`.
    """

    def __init__(self, endpoint: str | None = None, api_key: str | None = None, enabled: bool = False):
        self.endpoint = endpoint
        self.api_key = api_key
        self.enabled = enabled

    def write(self, entries: list[ParsedLogEntry]) -> None:
        if not self.enabled:
            logger.debug(
                "OrcristSink disabled (no confirmed API contract yet); skipping %d entries",
                len(entries),
            )
            return
        raise NotImplementedError(
            "Orcrist endpoint/auth/data-contract details are not yet available. "
            "Implement the request here once the team has a confirmed API contract."
        )
