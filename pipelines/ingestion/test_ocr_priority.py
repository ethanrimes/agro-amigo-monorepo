"""Private policy tests; no provider, DB or production changes."""
import unittest
from pipelines.ingestion import ocr as m

class OCRPriority(unittest.TestCase):
 def test_city_goes_first_at_new_day(self):
  self.assertEqual(m._priority_schedule(['city1','city2'],['pork1','pork2'],0,0,24,16,2),['city1','pork1'])
 def test_existing_external_attempts_preserve_city_reserve(self):
  self.assertEqual(m._priority_schedule(['city1','city2'],['pork1'],0,16,24,16,2),['city1','city2'])
 def test_other_lane_gets_fair_turn_under_city_backlog(self):
  self.assertEqual(m._priority_schedule(['city1','city2'],['pork1','pork2'],12,0,24,16,2),['pork1','pork2'])
 def test_city_cap_switches_to_other(self):
  self.assertEqual(m._priority_schedule(['city1','city2'],['pork1'],24,0,24,16,2),['pork1','city1'])
 def test_full_quotas_still_schedule_cached_candidates(self):
  self.assertEqual(m._priority_schedule(['city1'],['pork1'],24,16,24,16,2),['city1','pork1'])
 def test_both_full_lanes_alternate_cached_work(self):
  self.assertEqual(m._priority_schedule(['city1','city2'],['pork1','pork2'],24,16,24,16,2),['city1','pork1'])
 def test_respects_limit_and_order_within_lane(self):
  self.assertEqual(m._priority_schedule(['city1','city2','city3'],['pork1'],0,16,24,16,2),['city1','city2'])
 def test_empty_city_lane_allows_other(self):
  self.assertEqual(m._priority_schedule([],['pork1','pork2'],0,0,24,16,2),['pork1','pork2'])

if __name__=='__main__':unittest.main()
