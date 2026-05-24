import 'translations.dart';

/// Returns the display name for a dimension row given the current locale.
///
/// Dimension tables (dim_category, dim_subcategory, dim_insumo_grupo,
/// dim_insumo_subgrupo) carry the Spanish `canonical_name` plus an optional
/// `name_en`. When the app is in English mode we prefer `name_en` but fall
/// back to `canonical_name` for rows that haven't been translated yet.
String dimDisplayName(
  Map? row,
  AppLocale locale, {
  String fallback = '',
}) {
  if (row == null) return fallback;
  if (locale == AppLocale.en) {
    final en = row['name_en'];
    if (en is String && en.isNotEmpty) return en;
  }
  final es = row['canonical_name'];
  if (es is String && es.isNotEmpty) return es;
  return fallback;
}
