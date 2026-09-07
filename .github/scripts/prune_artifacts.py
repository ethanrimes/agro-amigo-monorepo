"""Keep the latest successful main build per platform for at most one day.

Only known AgroAmigo build artifacts are managed. Workflow logs, caches,
release records and files stored in Apple, Google or Azure are untouched.
Defaults to a read-only preview; --apply performs the deletions.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import subprocess

RELEASE_NAMES = {"agroamigo-native-ipa", "agroamigo-android-demo"}
OBSOLETE_NAMES = {"Runner-app", "agroamigo-react-ipa"}


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def retention_plan(artifacts, runs, now):
    cutoff = now - timedelta(days=1)
    keep, delete, retained_names = [], [], set()
    for artifact in sorted(artifacts, key=lambda a: (a["created_at"], a["id"]), reverse=True):
        name = artifact["name"]
        if name not in RELEASE_NAMES | OBSOLETE_NAMES:
            continue
        run = runs[artifact["workflow_run"]["id"]]
        # Another build may have uploaded a file but not finished yet.
        if run["status"] != "completed":
            continue
        current_release = (
            name in RELEASE_NAMES
            and run["conclusion"] == "success"
            and run["head_branch"] == "main"
            and not artifact["expired"]
            and timestamp(artifact["created_at"]) > cutoff
            and name not in retained_names
        )
        if current_release:
            keep.append(artifact)
            retained_names.add(name)
        else:
            delete.append(artifact)
    return keep, delete


def read_api(path, *, paginate=False):
    args = ["gh", "api", path]
    if paginate:
        args += ["--paginate", "--slurp"]
    return json.loads(subprocess.check_output(args, text=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "ethanrimes/agro-amigo-monorepo"))
    args = parser.parse_args()
    base = f"repos/{args.repo}/actions"
    pages = read_api(f"{base}/artifacts?per_page=100", paginate=True)
    artifacts = [artifact for page in pages for artifact in page["artifacts"]]
    run_ids = {a["workflow_run"]["id"] for a in artifacts if a["name"] in RELEASE_NAMES | OBSOLETE_NAMES}
    runs = {run_id: read_api(f"{base}/runs/{run_id}") for run_id in sorted(run_ids)}
    keep, delete = retention_plan(artifacts, runs, datetime.now(timezone.utc))
    print(json.dumps({
        "mode": "apply" if args.apply else "preview",
        "keep": [{"id": a["id"], "name": a["name"]} for a in keep],
        "delete_count": len(delete),
        "unexpired_bytes_to_remove": sum(a["size_in_bytes"] for a in delete if not a["expired"]),
        "already_expired_count": sum(a["expired"] for a in delete),
    }, indent=2), flush=True)
    if args.apply:
        for artifact in delete:
            subprocess.run(["gh", "api", "--method", "DELETE", f"{base}/artifacts/{artifact['id']}"], check=True)
            print(f"Deleted {artifact['name']} ({artifact['id']})", flush=True)


if __name__ == "__main__":
    main()
