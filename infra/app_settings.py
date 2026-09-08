"""Azure owns production configuration; releases only fill missing settings.

Credentials never appear in command arguments, logs or deployment ZIPs. Required
host settings may change with the runtime; operator-managed settings survive.
"""

import json
import tempfile
from pathlib import Path

from infra.provision import GROUP, LOCAL, az, private_write


def configure_app(kind, app, defaults, required=None):
    def read():
        return {
            row["name"]: row["value"]
            for row in az(kind, "config", "appsettings", "list", "-g", GROUP, "-n", app)
        }

    current = read()
    changes = {
        key: str(value)
        for key, value in defaults.items()
        if key not in current and value is not None
    }
    changes.update(
        {
            key: str(value)
            for key, value in (required or {}).items()
            if current.get(key) != str(value)
        }
    )
    if changes:
        with tempfile.TemporaryDirectory(
            prefix="app-settings-", dir=LOCAL
        ) as directory:
            path = Path(directory) / "settings.json"
            private_write(path, json.dumps(changes))
            az(
                kind,
                "config",
                "appsettings",
                "set",
                "-g",
                GROUP,
                "-n",
                app,
                "--settings",
                "@" + str(path),
            )
        actual = read()
        if any(actual.get(key) != value for key, value in changes.items()):
            raise RuntimeError("Azure settings verification failed; values omitted")
    print(
        f"Verified remote configuration for {app}; {len(changes)} settings updated.",
        flush=True,
    )
