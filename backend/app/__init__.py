"""Health Pulse backend.

The version guard below runs before any other module is imported, so an
unsupported interpreter produces an explanation rather than a confusing error
from deep inside a dependency.
"""

import sys

MINIMUM_PYTHON = (3, 11)

if sys.version_info < MINIMUM_PYTHON:  # pragma: no cover - depends on interpreter
    _required = ".".join(str(part) for part in MINIMUM_PYTHON)
    _running = ".".join(str(part) for part in sys.version_info[:3])
    raise RuntimeError(
        f"Health Pulse needs Python {_required} or newer, but this environment is "
        f"running {_running}.\n"
        f"  interpreter: {sys.executable}\n"
        "\n"
        "macOS ships Python 3.9 as /usr/bin/python3, and `python` is commonly aliased "
        "to it, so `python -m venv .venv` can quietly build the environment on 3.9. "
        "Without this check the first symptom is a TypeError about the `|` operator "
        "in app/config.py, which does not point at the real cause.\n"
        "\n"
        "Recreate the environment with a newer interpreter:\n"
        "    rm -rf .venv\n"
        "    python3.11 -m venv .venv    # or any newer python3.x on your PATH\n"
        "    .venv/bin/pip install -r requirements-dev.txt"
    )
