import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../translations/translations.dart';

enum MarketLevel { nacional, departamento, ciudad, mercado }

class DefaultMarket {
  final MarketLevel level;
  final String? id;
  final String name;
  const DefaultMarket({required this.level, this.id, required this.name});

  Map<String, dynamic> toJson() => {
        'level': level.name,
        'id': id,
        'name': name,
      };
  static DefaultMarket fromJson(Map<String, dynamic> j) => DefaultMarket(
        level: MarketLevel.values.firstWhere(
            (l) => l.name == j['level'],
            orElse: () => MarketLevel.nacional),
        id: j['id'] as String?,
        name: j['name'] as String? ?? 'Promedio nacional',
      );
}

class ChartSettings {
  final bool showAvgLine;
  final bool showTrendLine;
  final bool showMinMaxCallouts;
  final bool showInteractiveCallout;
  const ChartSettings({
    this.showAvgLine = true,
    this.showTrendLine = false,
    this.showMinMaxCallouts = true,
    this.showInteractiveCallout = true,
  });
  ChartSettings copyWith({
    bool? showAvgLine,
    bool? showTrendLine,
    bool? showMinMaxCallouts,
    bool? showInteractiveCallout,
  }) =>
      ChartSettings(
        showAvgLine: showAvgLine ?? this.showAvgLine,
        showTrendLine: showTrendLine ?? this.showTrendLine,
        showMinMaxCallouts: showMinMaxCallouts ?? this.showMinMaxCallouts,
        showInteractiveCallout:
            showInteractiveCallout ?? this.showInteractiveCallout,
      );
  Map<String, dynamic> toJson() => {
        'showAvgLine': showAvgLine,
        'showTrendLine': showTrendLine,
        'showMinMaxCallouts': showMinMaxCallouts,
        'showInteractiveCallout': showInteractiveCallout,
      };
  static ChartSettings fromJson(Map<String, dynamic> j) => ChartSettings(
        showAvgLine: j['showAvgLine'] as bool? ?? true,
        showTrendLine: j['showTrendLine'] as bool? ?? false,
        showMinMaxCallouts: j['showMinMaxCallouts'] as bool? ?? true,
        showInteractiveCallout: j['showInteractiveCallout'] as bool? ?? true,
      );
}

class AppSettings {
  final DefaultMarket defaultMarket;
  final double fontSizeScale;
  final ChartSettings chart;
  final AppLocale locale;
  final bool commentsEnabled;

  const AppSettings({
    this.defaultMarket =
        const DefaultMarket(level: MarketLevel.nacional, name: 'Promedio nacional'),
    this.fontSizeScale = 1,
    this.chart = const ChartSettings(),
    this.locale = AppLocale.es,
    this.commentsEnabled = true,
  });

  AppSettings copyWith({
    DefaultMarket? defaultMarket,
    double? fontSizeScale,
    ChartSettings? chart,
    AppLocale? locale,
    bool? commentsEnabled,
  }) =>
      AppSettings(
        defaultMarket: defaultMarket ?? this.defaultMarket,
        fontSizeScale: fontSizeScale ?? this.fontSizeScale,
        chart: chart ?? this.chart,
        locale: locale ?? this.locale,
        commentsEnabled: commentsEnabled ?? this.commentsEnabled,
      );

  Map<String, dynamic> toJson() => {
        'defaultMarket': defaultMarket.toJson(),
        'fontSizeScale': fontSizeScale,
        'chart': chart.toJson(),
        'locale': locale.name,
        'commentsEnabled': commentsEnabled,
      };

  static AppSettings fromJson(Map<String, dynamic> j) => AppSettings(
        defaultMarket: j['defaultMarket'] != null
            ? DefaultMarket.fromJson(j['defaultMarket'] as Map<String, dynamic>)
            : const DefaultMarket(level: MarketLevel.nacional, name: 'Promedio nacional'),
        fontSizeScale: (j['fontSizeScale'] as num?)?.toDouble() ?? 1,
        chart: j['chart'] != null
            ? ChartSettings.fromJson(j['chart'] as Map<String, dynamic>)
            : const ChartSettings(),
        locale: AppLocale.values
            .firstWhere((l) => l.name == j['locale'], orElse: () => AppLocale.es),
        commentsEnabled: j['commentsEnabled'] as bool? ?? true,
      );
}

class SettingsProvider extends ChangeNotifier {
  static const _storageKey = 'agroamigo_settings';

  AppSettings _settings = const AppSettings();
  bool _ready = false;

  AppSettings get settings => _settings;
  bool get ready => _ready;
  Translations get t => getTranslations(_settings.locale);

  Future<void> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_storageKey);
      if (raw != null) {
        _settings = AppSettings.fromJson(jsonDecode(raw) as Map<String, dynamic>);
      }
    } catch (_) {
      // fall through
    }
    _ready = true;
    notifyListeners();
  }

  Future<void> _persist(AppSettings next) async {
    _settings = next;
    notifyListeners();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_storageKey, jsonEncode(next.toJson()));
  }

  Future<void> updateDefaultMarket(DefaultMarket m) =>
      _persist(_settings.copyWith(defaultMarket: m));
  Future<void> updateFontSizeScale(double s) =>
      _persist(_settings.copyWith(fontSizeScale: s));
  Future<void> updateChartSettings(ChartSettings c) =>
      _persist(_settings.copyWith(chart: c));
  Future<void> updateLocale(AppLocale l) =>
      _persist(_settings.copyWith(locale: l));
  Future<void> updateCommentsEnabled(bool b) =>
      _persist(_settings.copyWith(commentsEnabled: b));
}
