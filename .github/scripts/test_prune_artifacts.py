from datetime import datetime, timezone
import unittest

from prune_artifacts import retention_plan


class RetentionTests(unittest.TestCase):
    now = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)

    def artifact(self, ident, *, name="agroamigo-native-ipa", created="2026-09-07T08:00:00Z", expired=False):
        return {"id": ident, "name": name, "created_at": created, "expired": expired, "workflow_run": {"id": ident}}

    def workflow(self, *, status="completed", conclusion="success", branch="main"):
        return {"status": status, "conclusion": conclusion, "head_branch": branch}

    def test_newest_success_per_platform_survives_failed_and_pr_builds(self):
        artifacts = [self.artifact(1), self.artifact(2), self.artifact(3), self.artifact(4), self.artifact(5, name="agroamigo-android-demo")]
        runs = {i: self.workflow() for i in range(1, 6)}
        runs[3] = self.workflow(conclusion="failure")
        runs[4] = self.workflow(branch="feature")
        keep, delete = retention_plan(artifacts, runs, self.now)
        self.assertEqual({a["id"] for a in keep}, {2, 5})
        self.assertEqual({a["id"] for a in delete}, {1, 3, 4})

    def test_old_expired_and_obsolete_copies_are_removed(self):
        artifacts = [self.artifact(1, created="2026-09-06T12:00:00Z"), self.artifact(2, expired=True), self.artifact(3, name="Runner-app"), self.artifact(4, name="agroamigo-react-ipa")]
        keep, delete = retention_plan(artifacts, {i: self.workflow() for i in range(1, 5)}, self.now)
        self.assertEqual(keep, [])
        self.assertEqual(len(delete), 4)

    def test_running_workflows_and_unknown_artifacts_are_untouched(self):
        artifacts = [self.artifact(1), self.artifact(2, name="Runner-app"), self.artifact(3, name="unrelated-report")]
        keep, delete = retention_plan(artifacts, {1: self.workflow(status="in_progress"), 2: self.workflow(status="queued")}, self.now)
        self.assertEqual((keep, delete), ([], []))


if __name__ == "__main__":
    unittest.main()
