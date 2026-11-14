"""Copy the authenticated astronaut UI to the legacy dashboard filename.

Health records are served only by the authenticated API and are never embedded
in a generated static HTML file.
"""

from __future__ import annotations

import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGIN_PAGE = os.path.join(ROOT, "app", "astronaut.html")
OUT = os.path.join(ROOT, "app", "dashboard.html")


def main() -> int:
    if not os.path.exists(LOGIN_PAGE):
        raise FileNotFoundError(f"missing sign-in page: {LOGIN_PAGE}")
    shutil.copyfile(LOGIN_PAGE, OUT)
    print(f"wrote authenticated sign-in page: {OUT}")
    print("Run scripts/serve_api.py to access private health reports.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
