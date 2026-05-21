/// Shared data classes used by both markets_api.dart and supply_api.dart.

class SupplySummary {
  final num totalKg;
  final num dailyAvgKg;
  final num numDays;
  final String? oldestObs;
  final String? newestObs;

  const SupplySummary({
    required this.totalKg,
    required this.dailyAvgKg,
    required this.numDays,
    this.oldestObs,
    this.newestObs,
  });

  factory SupplySummary.fromMap(Map<String, dynamic> row) => SupplySummary(
        totalKg: (row['total_kg'] as num?) ?? 0,
        dailyAvgKg: (row['daily_avg_kg'] as num?) ?? 0,
        numDays: (row['num_days'] as num?) ?? 0,
        oldestObs: row['oldest_obs'] as String?,
        newestObs: row['newest_obs'] as String?,
      );
}
