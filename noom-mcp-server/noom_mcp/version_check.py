"""Upstream version pin.

The only thing to update when pulling a new upstream release:
  1. Bump PATCHED_UPSTREAM_VERSION to the new version
  2. Re-validate that the patches still apply correctly
  3. Restart the server
"""

import logging

logger = logging.getLogger(__name__)

# Bump this (and re-validate) every time you pull a new upstream release.
PATCHED_UPSTREAM_VERSION = "0.1.12"


class UpstreamChangedError(RuntimeError):
    """Raised when the installed upstream version doesn't match the pin.

    Do not swallow this error.  Re-validate the patches against the new
    version, then bump PATCHED_UPSTREAM_VERSION above.
    """


def check_upstream_version() -> None:
    """Fail fast if the installed upstream version doesn't match the pin.

    Raises:
        UpstreamChangedError: If the versions don't match.
    """
    from databricks_tools_core.identity import PRODUCT_VERSION

    if PRODUCT_VERSION != PATCHED_UPSTREAM_VERSION:
        raise UpstreamChangedError(
            f"Upstream version mismatch — patches not validated for this version.\n"
            f"  Validated against: {PATCHED_UPSTREAM_VERSION}\n"
            f"  Installed version: {PRODUCT_VERSION}\n"
            f"  Action: test the patches against v{PRODUCT_VERSION}, then set "
            f"PATCHED_UPSTREAM_VERSION = {PRODUCT_VERSION!r} in version_check.py."
        )

    logger.info("Upstream version check passed (v%s)", PRODUCT_VERSION)
