"""Shared constants for Mochi's self-contained updater package."""

OFFICIAL_REPOSITORY = "miflow13/mochi-desktop"

# "release" follows GitHub's latest published (non-prerelease) release; "main"
# follows every merged change and is meant for alpha testers.
RELEASE_CHANNEL = "release"
MAIN_CHANNEL = "main"
UPDATE_CHANNELS = (RELEASE_CHANNEL, MAIN_CHANNEL)
DEFAULT_UPDATE_CHANNEL = RELEASE_CHANNEL
