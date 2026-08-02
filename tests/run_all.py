#!/usr/bin/env python3
"""Run every PrepHero suite.

    python3 tests/run_all.py

Needs nothing but a Mac: JavaScriptCore ships with the OS, and the whole app is
one file, so there is no build step and no dependency to install.
"""

import sys

import test_api
import test_auth
import test_commands
import test_images
import test_sessions
import test_sync
from harness import report


def main():
    results = {}
    results.update(test_auth.main())
    results.update(test_sessions.main())
    results.update(test_api.main())
    results.update(test_commands.main())
    results.update(test_images.main())
    results.update(test_sync.main())
    return report(results)


if __name__ == "__main__":
    sys.exit(main())
