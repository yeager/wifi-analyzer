#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${RELEASE_TAG:-}" ]]; then
    echo "RELEASE_TAG must name the versioned release to publish." >&2
    exit 2
fi
if [[ "$#" -eq 0 ]]; then
    echo "Provide at least one release asset." >&2
    exit 2
fi

if gh release view "$RELEASE_TAG" >/dev/null 2>&1; then
    gh release upload "$RELEASE_TAG" "$@" --clobber
else
    gh release create "$RELEASE_TAG" \
        --verify-tag \
        --generate-notes \
        --title "WiFi Analyzer $RELEASE_TAG" \
        "$@"
fi
