import 'package:flutter/cupertino.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:provider/provider.dart';
import 'package:agroamigo_iphone/theme/theme.dart';
import 'package:agroamigo_iphone/state/settings_provider.dart';
import 'package:agroamigo_iphone/services/format.dart';

/// Port of `LineChart.tsx`.
///
/// Features:
/// - Time-proportional x-axis (right edge = today; gap visible when stale).
/// - Optional min/max band lines.
/// - Average line (dashed), controlled by [ChartSettings.showAvgLine].
/// - Trend line (least-squares regression), [ChartSettings.showTrendLine].
/// - Min/max callout dots + labels, [ChartSettings.showMinMaxCallouts].
/// - Interactive touch callout, [ChartSettings.showInteractiveCallout].
/// - Horizontal scroll when [minPointSpacing] causes the chart to exceed [width].
/// - Legend row below chart.
class AppLineChartPoint {
  const AppLineChartPoint({
    required this.date,
    required this.value,
    this.min,
    this.max,
  });

  final String date;
  final double value;
  final double? min;
  final double? max;
}

class AppLineChart extends StatefulWidget {
  const AppLineChart({
    super.key,
    required this.data,
    required this.width,
    required this.height,
    this.color,
    this.showBands = false,
    this.formatValue,
    this.minPointSpacing,
  });

  final List<AppLineChartPoint> data;
  final double width;
  final double height;
  final Color? color;
  final bool showBands;
  final String Function(double)? formatValue;
  final double? minPointSpacing;

  @override
  State<AppLineChart> createState() => _AppLineChartState();
}

// Least-squares linear regression over indexed points.
({double slope, double intercept})? _linearRegression(
    List<double> values) {
  final n = values.length;
  if (n < 2) return null;
  double sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
  for (int i = 0; i < n; i++) {
    sumX += i;
    sumY += values[i];
    sumXY += i * values[i];
    sumX2 += i * i.toDouble();
  }
  final denom = n * sumX2 - sumX * sumX;
  if (denom == 0) return null;
  final slope = (n * sumXY - sumX * sumY) / denom;
  final intercept = (sumY - slope * sumX) / n;
  return (slope: slope, intercept: intercept);
}

class _AppLineChartState extends State<AppLineChart> {
  int? _touchedIdx;

  @override
  Widget build(BuildContext context) {
    final sp = context.watch<SettingsProvider>();
    final chartCfg = sp.settings.chart;
    final t = sp.t;
    final color = widget.color ?? AppColors.primary;
    final fmt = widget.formatValue ?? formatCOPCompact;

    final data = widget.data;
    if (data.isEmpty) {
      return SizedBox(width: widget.width, height: widget.height);
    }

    // Compute render width (expand for minPointSpacing scrolling).
    final renderW = (widget.minPointSpacing != null && data.length > 1)
        ? (data.length * widget.minPointSpacing!).clamp(widget.width, double.infinity)
        : widget.width;
    final scrolls = renderW > widget.width;

    // Y range.
    final allY = data.expand((d) => [d.min ?? d.value, d.max ?? d.value, d.value]);
    final rawMin = allY.reduce((a, b) => a < b ? a : b);
    final rawMax = allY.reduce((a, b) => a > b ? a : b);
    final minY = rawMin * 0.95;
    final maxY = rawMax * 1.05;

    // Timestamps for x-axis (time-proportional).
    final timestamps = data
        .map((d) => DateTime.parse('${d.date}T00:00:00').millisecondsSinceEpoch.toDouble())
        .toList();
    final today = DateTime.now();
    final todayT = DateTime(today.year, today.month, today.day)
        .millisecondsSinceEpoch
        .toDouble();
    final minT = timestamps.first;
    final maxT = todayT > timestamps.last ? todayT : timestamps.last;

    // Map timestamp → FlSpot x in [0, renderW-ish].
    // fl_chart uses the raw values as x, so we pass actual timestamps.
    double tToX(double ts) => ts; // fl_chart handles scale via minX/maxX.

    final mainSpots = List.generate(
        data.length, (i) => FlSpot(timestamps[i], data[i].value));

    // Average.
    final avgValue = data.map((d) => d.value).reduce((a, b) => a + b) / data.length;

    // Trend regression.
    final trend = chartCfg.showTrendLine
        ? _linearRegression(data.map((d) => d.value).toList())
        : null;

    // Min/max indices.
    int minIdx = 0, maxIdx = 0;
    if (data.length > 2) {
      for (int i = 1; i < data.length; i++) {
        if (data[i].value < data[minIdx].value) minIdx = i;
        if (data[i].value > data[maxIdx].value) maxIdx = i;
      }
    }

    // Band spots.
    final minBandSpots = widget.showBands
        ? List.generate(data.length,
            (i) => FlSpot(timestamps[i], data[i].min ?? data[i].value))
        : <FlSpot>[];
    final maxBandSpots = widget.showBands
        ? List.generate(data.length,
            (i) => FlSpot(timestamps[i], data[i].max ?? data[i].value))
        : <FlSpot>[];

    // X-axis labels (5 evenly-spaced calendar dates).
    const numXLabels = 5;
    final spansYears = DateTime.fromMillisecondsSinceEpoch(minT.toInt()).year !=
        DateTime.fromMillisecondsSinceEpoch(maxT.toInt()).year;
    final currentYear = DateTime.now().year;

    String fmtXDate(double ts) {
      final d = DateTime.fromMillisecondsSinceEpoch(ts.toInt());
      final iso = '${d.year}-${d.month.toString().padLeft(2,'0')}-${d.day.toString().padLeft(2,'0')}';
      final label = formatDateShort(iso);
      if (spansYears) return "$label '${d.year.toString().substring(2)}";
      if (d.year < currentYear) return "$label '${d.year.toString().substring(2)}";
      return label;
    }

    // Build line bars.
    final lineBars = <LineChartBarData>[
      // Main line.
      LineChartBarData(
        spots: mainSpots,
        isCurved: false,
        color: color,
        barWidth: 2,
        isStrokeCapRound: true,
        dotData: FlDotData(
          show: chartCfg.showMinMaxCallouts && data.length > 2 && minIdx != maxIdx,
          checkToShowDot: (spot, _) {
            final i = mainSpots.indexWhere((s) => s.x == spot.x && s.y == spot.y);
            return i == minIdx || i == maxIdx;
          },
          getDotPainter: (spot, _, __, i) {
            final isMax = i == maxIdx;
            return FlDotCirclePainter(
              radius: 3,
              color: isMax ? AppColors.accentOrange : AppColors.accentBlue,
              strokeWidth: 0,
            );
          },
        ),
        showingIndicators: chartCfg.showMinMaxCallouts &&
                data.length > 2 &&
                minIdx != maxIdx
            ? [minIdx, maxIdx]
            : [],
      ),
      // Trend line.
      if (trend != null)
        LineChartBarData(
          spots: [
            FlSpot(timestamps.first, trend.intercept),
            FlSpot(timestamps.last,
                trend.slope * (data.length - 1) + trend.intercept),
          ],
          isCurved: false,
          color: AppColors.accentOrange.withOpacity(0.6),
          barWidth: 1.5,
          dashArray: [8, 4],
          dotData: const FlDotData(show: false),
          belowBarData: BarAreaData(show: false),
        ),
      // Band max.
      if (widget.showBands)
        LineChartBarData(
          spots: maxBandSpots,
          color: AppColors.textTertiary.withOpacity(0.4),
          barWidth: 0.5,
          dashArray: [3, 3],
          dotData: const FlDotData(show: false),
          belowBarData: BarAreaData(show: false),
        ),
      // Band min.
      if (widget.showBands)
        LineChartBarData(
          spots: minBandSpots,
          color: AppColors.textTertiary.withOpacity(0.4),
          barWidth: 0.5,
          dashArray: [3, 3],
          dotData: const FlDotData(show: false),
          belowBarData: BarAreaData(show: false),
        ),
    ];

    // Always-on min/max tooltip indicators.
    final showingIndicators = <ShowingTooltipIndicators>[];
    if (chartCfg.showMinMaxCallouts && data.length > 2 && minIdx != maxIdx) {
      showingIndicators.add(ShowingTooltipIndicators([
        LineBarSpot(lineBars[0], 0, mainSpots[maxIdx]),
      ]));
      showingIndicators.add(ShowingTooltipIndicators([
        LineBarSpot(lineBars[0], 0, mainSpots[minIdx]),
      ]));
    }
    // Touch callout indicator (overrides always-on when user is touching).
    if (chartCfg.showInteractiveCallout &&
        _touchedIdx != null &&
        _touchedIdx! < data.length) {
      showingIndicators
        ..clear()
        ..add(ShowingTooltipIndicators([
          LineBarSpot(lineBars[0], 0, mainSpots[_touchedIdx!]),
        ]));
    }

    final chart = SizedBox(
      width: renderW,
      height: widget.height,
      child: LineChart(
        LineChartData(
          minX: minT,
          maxX: maxT,
          minY: minY,
          maxY: maxY,
          clipData: const FlClipData.all(),
          gridData: FlGridData(
            show: true,
            drawVerticalLine: false,
            getDrawingHorizontalLine: (_) => FlLine(
              color: AppColors.borderLight,
              strokeWidth: 1,
            ),
          ),
          borderData: FlBorderData(show: false),
          titlesData: FlTitlesData(
            topTitles:
                const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles:
                const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            leftTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 50,
                interval: (maxY - minY) / 2,
                getTitlesWidget: (value, meta) => SideTitleWidget(
                  meta: meta,
                  child: Text(fmt(value),
                      style: const TextStyle(
                          fontSize: 9, color: AppColors.textTertiary)),
                ),
              ),
            ),
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                reservedSize: 28,
                interval: (maxT - minT) / (numXLabels - 1),
                getTitlesWidget: (value, meta) {
                  if (value < minT - 1 || value > maxT + 1) {
                    return const SizedBox.shrink();
                  }
                  return SideTitleWidget(
                    meta: meta,
                    child: Text(fmtXDate(value),
                        style: const TextStyle(
                            fontSize: 9, color: AppColors.textTertiary)),
                  );
                },
              ),
            ),
          ),
          lineBarsData: lineBars,
          extraLinesData: ExtraLinesData(
            horizontalLines: chartCfg.showAvgLine && data.length > 1
                ? [
                    HorizontalLine(
                      y: avgValue,
                      color: color.withOpacity(0.4),
                      strokeWidth: 1,
                      dashArray: [6, 4],
                      label: HorizontalLineLabel(
                        show: true,
                        alignment: Alignment.topRight,
                        padding: const EdgeInsets.only(right: 4, bottom: 2),
                        style: TextStyle(
                            fontSize: 9,
                            color: color.withOpacity(0.6)),
                        labelResolver: (_) => fmt(avgValue),
                      ),
                    ),
                  ]
                : [],
          ),
          lineTouchData: LineTouchData(
            enabled: chartCfg.showInteractiveCallout,
            handleBuiltInTouches: true,
            touchCallback: (event, response) {
              if (!chartCfg.showInteractiveCallout) return;
              if (event is FlTapUpEvent ||
                  event is FlLongPressEnd ||
                  event is FlPointerExitEvent) {
                setState(() => _touchedIdx = null);
                return;
              }
              final spots = response?.lineBarSpots;
              if (spots != null && spots.isNotEmpty) {
                final s =
                    spots.where((s) => s.barIndex == 0).firstOrNull ?? spots.first;
                setState(() => _touchedIdx = s.spotIndex);
              }
            },
            touchTooltipData: LineTouchTooltipData(
              getTooltipColor: (_) => AppColors.dark.withOpacity(0.9),
              tooltipRoundedRadius: 4,
              fitInsideHorizontally: true,
              fitInsideVertically: false,
              getTooltipItems: (spots) {
                return spots.map((spot) {
                  if (spot.barIndex != 0) {
                    return const LineTooltipItem('', TextStyle());
                  }
                  final idx = spot.spotIndex;
                  final point = data[idx];
                  final isMax = idx == maxIdx;
                  final isMin = idx == minIdx;
                  final labelColor = isMax
                      ? AppColors.accentOrange
                      : isMin
                          ? AppColors.accentBlue
                          : color;
                  return LineTooltipItem(
                    fmt(point.value),
                    TextStyle(
                        color: labelColor,
                        fontSize: 10,
                        fontWeight: FontWeight.w600),
                    children: [
                      TextSpan(
                        text: '\n${formatDateShort(point.date)}',
                        style: const TextStyle(
                            color: Color(0xFFCCCCCC), fontSize: 8),
                      ),
                    ],
                  );
                }).toList();
              },
            ),
          ),
          showingTooltipIndicators: showingIndicators,
        ),
        duration: Duration.zero,
      ),
    );

    // Legend items.
    final legendItems = <({Color color, String label, bool dashed})>[];
    if (chartCfg.showAvgLine && data.length > 1) {
      legendItems.add((color: color, label: t.settings_chart_avg_line, dashed: true));
    }
    if (trend != null) {
      legendItems.add((
        color: AppColors.accentOrange,
        label: t.settings_chart_trend_line,
        dashed: true
      ));
    }
    if (chartCfg.showMinMaxCallouts && data.length > 2 && minIdx != maxIdx) {
      legendItems.add((color: AppColors.accentOrange, label: t.product_max, dashed: false));
      legendItems.add((color: AppColors.accentBlue, label: t.product_min, dashed: false));
    }

    final legendWidget = legendItems.isNotEmpty
        ? Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Wrap(
              spacing: AppSpacing.md,
              runSpacing: 2,
              alignment: WrapAlignment.center,
              children: legendItems.map((item) {
                return Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (item.dashed)
                      CustomPaint(
                        size: const Size(16, 8),
                        painter: _DashLinePainter(color: item.color),
                      )
                    else
                      Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: item.color,
                          shape: BoxShape.circle,
                        ),
                      ),
                    const SizedBox(width: 4),
                    Text(item.label,
                        style: const TextStyle(
                            fontSize: AppFontSize.xs - 1,
                            color: AppColors.textTertiary)),
                  ],
                );
              }).toList(),
            ),
          )
        : null;

    final body = Column(
      children: [
        if (scrolls)
          SizedBox(
            width: widget.width,
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: chart,
            ),
          )
        else
          chart,
        if (legendWidget != null) legendWidget,
      ],
    );

    return body;
  }
}

class _DashLinePainter extends CustomPainter {
  const _DashLinePainter({required this.color});
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeWidth = 1.5;
    const dashLen = 4.0;
    const gapLen = 2.0;
    double x = 0;
    final y = size.height / 2;
    while (x < size.width) {
      canvas.drawLine(Offset(x, y), Offset((x + dashLen).clamp(0, size.width), y), paint);
      x += dashLen + gapLen;
    }
  }

  @override
  bool shouldRepaint(_DashLinePainter old) => old.color != color;
}
