"""Deploy the checked standalone build, exclude credentials and verify the new release."""

import json
import sys
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from infra.app_settings import configure_app
from infra.provision import APP, GROUP, LOCAL, ROOT, SERVER, az


def deploy():
    config = json.loads((LOCAL / "database.json").read_text())
    web = ROOT / "apps/web"
    standalone = web / ".next/standalone"
    if not (standalone / "apps/web/server.js").exists():
        raise RuntimeError("Run npm run build first")
    app = az("webapp", "show", "-g", GROUP, "-n", APP)
    ips = sorted(set(app["outboundIpAddresses"].split(",")))
    current = az(
        "postgres",
        "flexible-server",
        "firewall-rule",
        "list",
        "-g",
        GROUP,
        "--server-name",
        SERVER,
    )
    allowed = {(r["startIpAddress"], r["endIpAddress"]) for r in current}
    for i, ip in enumerate(ips):
        if (ip, ip) not in allowed:
            az(
                "postgres",
                "flexible-server",
                "firewall-rule",
                "create",
                "-g",
                GROUP,
                "--server-name",
                SERVER,
                "--name",
                f"agroamigo-web-{i}",
                "--start-ip-address",
                ip,
                "--end-ip-address",
                ip,
            )
    print(f"Confirmed {len(ips)} exact web host outbound IPs.", flush=True)
    connection = f"postgresql://agro_reader:{quote(config['appPassword'], safe='')}@{config['host']}:5432/{config['database']}"
    configure_app(
        "webapp",
        APP,
        {"DATABASE_URL": connection, "SOURCE_STORAGE_ACCOUNT": "agroamigodata9a04", "SOURCE_WORKBOOK_API_URL": "https://agroamigo-data-9a04.azurewebsites.net"},
        {
            "NODE_ENV": "production",
            "HOSTNAME": "0.0.0.0",
            "PORT": "8080",
            "WEBSITE_RUN_FROM_PACKAGE": "1",
            "SCM_DO_BUILD_DURING_DEPLOY": "false",
            "WEBSITE_WARMUP_PATH": "/api/health",
        },
    )
    release = {
        "id": uuid.uuid4().hex,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (web / "public/release.json").write_text(json.dumps(release))
    bundle = LOCAL / "site.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in standalone.rglob("*"):
            if path.is_file() and not any(
                part.startswith(".env") for part in path.parts
            ):
                archive.write(path, path.relative_to(standalone))
        for directory, target in [
            ("public", "apps/web/public"),
            (".next/static", "apps/web/.next/static"),
        ]:
            for path in (web / directory).rglob("*"):
                if path.is_file():
                    archive.write(
                        path, target + "/" + str(path.relative_to(web / directory))
                    )
        if any(
            any(x.startswith(".env") for x in p.split("/")) for p in archive.namelist()
        ):
            raise RuntimeError("Dotenv in deployment bundle")
    print(
        f"Deploying {bundle.stat().st_size // 1024 // 1024} MiB, release {release['id']}",
        flush=True,
    )
    az(
        "webapp",
        "config",
        "set",
        "-g",
        GROUP,
        "-n",
        APP,
        "--startup-file",
        "node apps/web/server.js",
    )
    az(
        "webapp",
        "deploy",
        "-g",
        GROUP,
        "-n",
        APP,
        "--src-path",
        str(bundle),
        "--type",
        "zip",
        "--clean",
        "true",
        "--restart",
        "true",
        "--track-status",
        "false",
        "--timeout",
        "180000",
    )
    base = "https://" + app["defaultHostName"]
    for attempt in range(40):
        try:
            with urllib.request.urlopen(
                base + "/release.json?v=" + release["id"], timeout=12
            ) as r:
                remote = json.load(r)
            with urllib.request.urlopen(base + "/api/health", timeout=12) as r:
                health = json.load(r)
            if remote == release and health.get("database") == "connected":
                print("Verified deployed release and database:", base, flush=True)
                return
        except Exception:
            pass
        if attempt % 3 == 0:
            print("Waiting for the new release to start…", flush=True)
        time.sleep(5)
    raise RuntimeError(
        "New release did not pass health verification; inspect Azure startup logs."
    )


if __name__ == "__main__":
    deploy()
