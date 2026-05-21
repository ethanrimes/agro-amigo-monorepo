import 'package:intl/intl.dart';

/// Port of `agroamigo-app/src/lib/format.ts`.

final _copFormatter = NumberFormat.currency(
  locale: 'es_CO',
  symbol: r'$',
  decimalDigits: 0,
);

String formatCOP(num? value) {
  if (value == null) return '—';
  return _copFormatter.format(value);
}

String formatCOPCompact(num? value) {
  if (value == null) return '—';
  if (value >= 1000000) return '\$${(value / 1000000).toStringAsFixed(1)}M';
  if (value >= 1000) return '\$${(value / 1000).round()}K';
  return '\$${value.round()}';
}

String formatPctChange(num? value) {
  if (value == null) return '—';
  final sign = value >= 0 ? '+' : '';
  return '$sign${value.toStringAsFixed(1)}%';
}

String formatKg(num? value) {
  if (value == null) return '—';
  if (value >= 1000000) return '${(value / 1000000).toStringAsFixed(1)}M kg';
  if (value >= 1000) return '${(value / 1000).toStringAsFixed(1)}K kg';
  return '${value.round()} kg';
}

const _shortMonthsEs = ['ene', 'feb', 'mar', 'abr', 'may', 'jun',
  'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

const _longMonthsEs = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
  'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

String formatDateShort(String dateStr) {
  final d = DateTime.parse('${dateStr}T00:00:00');
  return '${d.day} ${_shortMonthsEs[d.month - 1]}';
}

String formatDateMedium(String dateStr) {
  final d = DateTime.parse('${dateStr}T00:00:00');
  return '${d.day} de ${_longMonthsEs[d.month - 1]} ${d.year}';
}

String formatPriceContext(String? presentation, String? units) {
  return [presentation, units].where((p) => p != null && p.isNotEmpty).join(' · ');
}

double pctChange(num oldVal, num newVal) {
  if (oldVal == 0) return 0;
  return ((newVal - oldVal) / oldVal) * 100;
}
