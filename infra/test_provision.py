"""Provisioning must not silently downsize an existing ingestion host."""

import unittest

from .provision import selected_app_service_sku


class HostCapacity(unittest.TestCase):
    def test_preserves_existing_capacity_and_allows_explicit_change(self):
        for sku in ("B1", "B2", "B3", "P1v3"):
            plans = [{"name": "agroamigo-demo-plan", "sku": {"name": sku}}]
            self.assertEqual(selected_app_service_sku(plans), sku)
            self.assertEqual(selected_app_service_sku(plans, "B2"), "B2")

    def test_new_plan_uses_validated_large_source_capacity(self):
        self.assertEqual(selected_app_service_sku([]), "B2")


if __name__ == "__main__":
    unittest.main()
