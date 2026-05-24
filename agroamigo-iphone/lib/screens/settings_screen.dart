import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import '../api/markets_api.dart';
import '../state/auth_provider.dart';
import '../state/settings_provider.dart';
import '../theme/theme.dart';
import '../translations/translations.dart';
import 'auth_screen.dart';

class _PickerItem {
  final String id;
  final String name;
  final String? subtitle;
  final MarketLevel level;
  const _PickerItem({
    required this.id,
    required this.name,
    this.subtitle,
    required this.level,
  });
}

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  final _searchCtrl = TextEditingController();
  String _search = '';
  List<_PickerItem> _allItems = [];
  bool _loadingItems = false;

  @override
  void initState() {
    super.initState();
    _loadItems();
    _searchCtrl.addListener(() {
      if (_searchCtrl.text != _search) {
        setState(() => _search = _searchCtrl.text);
      }
    });
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadItems() async {
    final t = context.read<SettingsProvider>().t;
    setState(() => _loadingItems = true);
    try {
      final markets = await getMarkets();
      final items = <_PickerItem>[];
      final seenDepts = <String>{};
      final seenCities = <String>{};

      for (final raw in markets) {
        final m = raw as Map<String, dynamic>;
        final city = m['dim_city'] as Map<String, dynamic>?;
        final dept = city == null
            ? null
            : city['dim_department'] as Map<String, dynamic>?;

        if (dept != null) {
          final id = dept['id']?.toString();
          if (id != null && seenDepts.add(id)) {
            items.add(_PickerItem(
              id: id,
              name: dept['canonical_name']?.toString() ?? '',
              subtitle: t.settings_department,
              level: MarketLevel.departamento,
            ));
          }
        }
        if (city != null) {
          final id = city['id']?.toString() ?? city['canonical_name']?.toString();
          if (id != null && seenCities.add(id)) {
            items.add(_PickerItem(
              id: id,
              name: city['canonical_name']?.toString() ?? '',
              subtitle: [
                t.settings_city,
                dept?['canonical_name']?.toString(),
              ].where((e) => e != null && e.isNotEmpty).join(' · '),
              level: MarketLevel.ciudad,
            ));
          }
        }
        final mid = m['id']?.toString();
        if (mid != null) {
          final where = [
            city?['canonical_name']?.toString(),
            dept?['canonical_name']?.toString(),
          ].where((e) => e != null && e!.isNotEmpty).join(', ');
          items.add(_PickerItem(
            id: mid,
            name: m['canonical_name']?.toString() ?? '',
            subtitle: ['Mercado', if (where.isNotEmpty) where].join(' · '),
            level: MarketLevel.mercado,
          ));
        }
      }
      if (mounted) setState(() => _allItems = items);
    } catch (_) {
      // swallow — settings still works without picker data
    } finally {
      if (mounted) setState(() => _loadingItems = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<SettingsProvider>();
    final auth = context.watch<AuthProvider>();
    final t = settings.t;
    final s = settings.settings;
    final scale = s.fontSizeScale;

    return CupertinoPageScaffold(
      navigationBar: CupertinoNavigationBar(
        backgroundColor: AppColors.dark,
        middle: Text(t.nav_settings,
            style: const TextStyle(color: AppColors.textInverse, fontWeight: FontWeight.w700)),
      ),
      child: SafeArea(
        child: ListView(
          padding: EdgeInsets.zero,
          children: [
            const SizedBox(height: AppSpacing.md),
            _defaultMarketSection(context, t, s, scale),
            _fontSizeSection(context, t, s, scale),
            _languageSection(context, t, s, scale),
            _chartsSection(context, t, s, scale),
            _commentsSection(context, t, s, scale),
            _accountSection(context, t, scale, auth),
            const SizedBox(height: AppSpacing.xxl),
          ],
        ),
      ),
    );
  }

  // -------- Default Market --------
  Widget _defaultMarketSection(
      BuildContext context, Translations t, AppSettings s, double scale) {
    final dm = s.defaultMarket;
    final levels = const [
      MarketLevel.nacional,
      MarketLevel.departamento,
      MarketLevel.ciudad,
      MarketLevel.mercado,
    ];

    return _section(
      title: t.settings_default_market,
      description: t.settings_default_market_desc,
      scale: scale,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          CupertinoSlidingSegmentedControl<MarketLevel>(
            groupValue: dm.level,
            onValueChanged: (lvl) {
              if (lvl == null) return;
              // Store an empty name; rendering uses DefaultMarket.displayName(t)
              // so the label always tracks the active locale.
              context.read<SettingsProvider>().updateDefaultMarket(
                    DefaultMarket(level: lvl, name: ''),
                  );
              _searchCtrl.clear();
            },
            children: {
              MarketLevel.nacional: _segLabel(t.settings_national_avg, scale),
              MarketLevel.departamento: _segLabel(t.settings_department, scale),
              MarketLevel.ciudad: _segLabel(t.settings_city, scale),
              MarketLevel.mercado: _segLabel(t.settings_specific_market, scale),
            },
          ),
          const SizedBox(height: AppSpacing.md),
          Container(
            padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md, vertical: AppSpacing.sm),
            decoration: BoxDecoration(
              color: const Color(0x1A2D7D46),
              borderRadius: BorderRadius.circular(AppRadius.sm),
            ),
            child: Row(
              children: [
                const Icon(CupertinoIcons.checkmark_alt_circle,
                    size: 18, color: AppColors.primary),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Text(
                    dm.level == MarketLevel.nacional || dm.id != null
                        ? dm.displayName(t)
                        : t.settings_select_option,
                    style: TextStyle(
                      fontSize: AppFontSize.sm * scale,
                      fontWeight: FontWeight.w600,
                      color: AppColors.primary,
                    ),
                  ),
                ),
              ],
            ),
          ),
          if (dm.level != MarketLevel.nacional) ...[
            const SizedBox(height: AppSpacing.md),
            _picker(t, s, scale),
          ],
        ],
      ),
    );
  }

  Widget _segLabel(String text, double scale) => Padding(
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
        child: Text(text,
            style: TextStyle(fontSize: AppFontSize.xs * scale),
            overflow: TextOverflow.ellipsis),
      );

  String _levelLabel(Translations t, MarketLevel lvl) {
    switch (lvl) {
      case MarketLevel.nacional:
        return t.settings_national_avg;
      case MarketLevel.departamento:
        return t.settings_department;
      case MarketLevel.ciudad:
        return t.settings_city;
      case MarketLevel.mercado:
        return t.settings_specific_market;
    }
  }

  Widget _picker(Translations t, AppSettings s, double scale) {
    final level = s.defaultMarket.level;
    final selectedId = s.defaultMarket.id;
    final q = _search.trim().toLowerCase();
    final pool = _allItems.where((i) => i.level == level).toList();
    final filtered = q.length < 2
        ? <_PickerItem>[]
        : pool
            .where((i) =>
                i.name.toLowerCase().contains(q) ||
                (i.subtitle?.toLowerCase().contains(q) ?? false))
            .toList();
    final shown = filtered.take(50).toList();

    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: AppColors.borderLight),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md, vertical: AppSpacing.sm),
            child: CupertinoSearchTextField(
              controller: _searchCtrl,
              placeholder: t.settings_search_placeholder,
              style: TextStyle(fontSize: AppFontSize.md * scale),
              onChanged: (v) => setState(() => _search = v),
            ),
          ),
          if (_loadingItems)
            const Padding(
              padding: EdgeInsets.all(AppSpacing.lg),
              child: CupertinoActivityIndicator(),
            )
          else if (q.length < 2)
            Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Text(
                t.settings_search_min_chars,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: AppFontSize.xs * scale,
                  color: AppColors.textTertiary,
                  fontStyle: FontStyle.italic,
                ),
              ),
            )
          else if (shown.isEmpty)
            Padding(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Text(t.settings_no_results,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: AppFontSize.sm * scale,
                    color: AppColors.textTertiary,
                  )),
            )
          else
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 320),
              child: ListView.separated(
                shrinkWrap: true,
                itemCount: shown.length,
                separatorBuilder: (_, __) => Container(
                  height: 0.5,
                  color: AppColors.borderLight,
                ),
                itemBuilder: (ctx, i) {
                  final item = shown[i];
                  final selected = selectedId == item.id;
                  IconData icon;
                  switch (item.level) {
                    case MarketLevel.departamento:
                      icon = CupertinoIcons.map;
                      break;
                    case MarketLevel.ciudad:
                      icon = CupertinoIcons.building_2_fill;
                      break;
                    case MarketLevel.mercado:
                      icon = CupertinoIcons.cart;
                      break;
                    case MarketLevel.nacional:
                      icon = CupertinoIcons.globe;
                      break;
                  }
                  return CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () {
                      context.read<SettingsProvider>().updateDefaultMarket(
                            DefaultMarket(
                                level: item.level,
                                id: item.id,
                                name: item.name),
                          );
                      _searchCtrl.clear();
                      setState(() => _search = '');
                    },
                    child: Container(
                      color: selected
                          ? const Color(0x142D7D46)
                          : AppColors.surface,
                      padding: const EdgeInsets.symmetric(
                          horizontal: AppSpacing.md,
                          vertical: AppSpacing.md),
                      child: Row(
                        children: [
                          Icon(icon,
                              size: 16, color: AppColors.textTertiary),
                          const SizedBox(width: AppSpacing.sm),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(item.name,
                                    style: TextStyle(
                                      fontSize: AppFontSize.md * scale,
                                      fontWeight: selected
                                          ? FontWeight.w600
                                          : FontWeight.w500,
                                      color: selected
                                          ? AppColors.primary
                                          : AppColors.textPrimary,
                                    )),
                                if (item.subtitle != null &&
                                    item.subtitle!.isNotEmpty)
                                  Text(item.subtitle!,
                                      style: TextStyle(
                                        fontSize: AppFontSize.xs * scale,
                                        color: AppColors.textTertiary,
                                      )),
                              ],
                            ),
                          ),
                          if (selected)
                            const Icon(CupertinoIcons.checkmark,
                                size: 18, color: AppColors.primary),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
          if (filtered.length > 50)
            Padding(
              padding: const EdgeInsets.all(AppSpacing.sm),
              child: Text(
                '${t.settings_showing_n_of} ${filtered.length}',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: AppFontSize.xs * scale,
                  color: AppColors.textTertiary,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ),
        ],
      ),
    );
  }

  // -------- Font Size --------
  Widget _fontSizeSection(
      BuildContext context, Translations t, AppSettings s, double scale) {
    final steps = [
      (t.settings_font_small, 0.85),
      (t.settings_font_normal, 1.0),
      (t.settings_font_large, 1.15),
      (t.settings_font_xlarge, 1.3),
    ];

    return _section(
      title: t.settings_font_size,
      description: t.settings_font_size_desc,
      scale: scale,
      child: Column(
        children: [
          Row(
            children: [
              for (final (label, step) in steps) ...[
                Expanded(
                  child: GestureDetector(
                    onTap: () => context
                        .read<SettingsProvider>()
                        .updateFontSizeScale(step),
                    child: Container(
                      margin: const EdgeInsets.symmetric(horizontal: 2),
                      padding: const EdgeInsets.symmetric(
                          vertical: AppSpacing.md),
                      decoration: BoxDecoration(
                        color: s.fontSizeScale == step
                            ? const Color(0x1A2D7D46)
                            : AppColors.surface,
                        borderRadius: BorderRadius.circular(AppRadius.md),
                        border: Border.all(
                          color: s.fontSizeScale == step
                              ? AppColors.primary
                              : AppColors.borderLight,
                        ),
                      ),
                      child: Column(
                        children: [
                          Text('Aa',
                              style: TextStyle(
                                fontSize: 15 * step,
                                fontWeight: FontWeight.w700,
                                color: s.fontSizeScale == step
                                    ? AppColors.primary
                                    : AppColors.textPrimary,
                              )),
                          const SizedBox(height: AppSpacing.xs),
                          Text(label,
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontSize: AppFontSize.xs,
                                color: s.fontSizeScale == step
                                    ? AppColors.primary
                                    : AppColors.textSecondary,
                              )),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          Container(
            padding: const EdgeInsets.all(AppSpacing.md),
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(AppRadius.md),
              border: Border.all(color: AppColors.borderLight),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(t.settings_preview,
                    style: TextStyle(
                      fontSize: AppFontSize.lg * s.fontSizeScale,
                      fontWeight: FontWeight.w700,
                      color: AppColors.textPrimary,
                    )),
                const SizedBox(height: AppSpacing.xs),
                Text(t.settings_preview_desc,
                    style: TextStyle(
                      fontSize: AppFontSize.sm * s.fontSizeScale,
                      color: AppColors.textSecondary,
                    )),
                const SizedBox(height: AppSpacing.xs),
                Text(r'$2.500/kg',
                    style: TextStyle(
                      fontSize: AppFontSize.md * s.fontSizeScale,
                      fontWeight: FontWeight.w600,
                      color: AppColors.primary,
                    )),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // -------- Language --------
  Widget _languageSection(
      BuildContext context, Translations t, AppSettings s, double scale) {
    return _section(
      title: t.settings_language,
      description: t.settings_language_desc,
      scale: scale,
      child: CupertinoSlidingSegmentedControl<AppLocale>(
        groupValue: s.locale,
        onValueChanged: (l) {
          if (l != null) context.read<SettingsProvider>().updateLocale(l);
        },
        children: {
          AppLocale.es: Padding(
            padding: const EdgeInsets.symmetric(
                vertical: AppSpacing.xs, horizontal: AppSpacing.lg),
            child: Text('Español',
                style: TextStyle(fontSize: AppFontSize.sm * scale)),
          ),
          AppLocale.en: Padding(
            padding: const EdgeInsets.symmetric(
                vertical: AppSpacing.xs, horizontal: AppSpacing.lg),
            child: Text('English',
                style: TextStyle(fontSize: AppFontSize.sm * scale)),
          ),
        },
      ),
    );
  }

  // -------- Charts --------
  Widget _chartsSection(
      BuildContext context, Translations t, AppSettings s, double scale) {
    return _section(
      title: t.settings_charts,
      description: t.settings_charts_desc,
      scale: scale,
      child: CupertinoListSection.insetGrouped(
        margin: EdgeInsets.zero,
        backgroundColor: AppColors.background,
        children: [
          _chartTile(t.settings_chart_avg_line, s.chart.showAvgLine, scale, (v) {
            context
                .read<SettingsProvider>()
                .updateChartSettings(s.chart.copyWith(showAvgLine: v));
          }),
          _chartTile(t.settings_chart_trend_line, s.chart.showTrendLine, scale,
              (v) {
            context
                .read<SettingsProvider>()
                .updateChartSettings(s.chart.copyWith(showTrendLine: v));
          }),
          _chartTile(t.settings_chart_min_max_callouts,
              s.chart.showMinMaxCallouts, scale, (v) {
            context
                .read<SettingsProvider>()
                .updateChartSettings(s.chart.copyWith(showMinMaxCallouts: v));
          }),
          _chartTile(t.settings_chart_interactive,
              s.chart.showInteractiveCallout, scale, (v) {
            context.read<SettingsProvider>().updateChartSettings(
                s.chart.copyWith(showInteractiveCallout: v));
          }),
        ],
      ),
    );
  }

  CupertinoListTile _chartTile(
      String label, bool value, double scale, ValueChanged<bool> onChanged) {
    return CupertinoListTile(
      title: Text(label, style: TextStyle(fontSize: AppFontSize.md * scale)),
      trailing: CupertinoSwitch(value: value, onChanged: onChanged),
    );
  }

  // -------- Comments --------
  Widget _commentsSection(
      BuildContext context, Translations t, AppSettings s, double scale) {
    return _section(
      title: t.settings_comments,
      description: t.settings_comments_desc,
      scale: scale,
      child: CupertinoListSection.insetGrouped(
        margin: EdgeInsets.zero,
        backgroundColor: AppColors.background,
        children: [
          CupertinoListTile(
            leading: Icon(CupertinoIcons.chat_bubble,
                color: s.commentsEnabled
                    ? AppColors.primary
                    : AppColors.textSecondary),
            title: Text(t.settings_comments_toggle,
                style: TextStyle(fontSize: AppFontSize.md * scale)),
            trailing: CupertinoSwitch(
              value: s.commentsEnabled,
              onChanged: (v) =>
                  context.read<SettingsProvider>().updateCommentsEnabled(v),
            ),
          ),
        ],
      ),
    );
  }

  // -------- Account --------
  Widget _accountSection(BuildContext context, Translations t, double scale,
      AuthProvider auth) {
    Widget body;
    if (auth.userId != null && auth.profile != null) {
      String memberSince = auth.profile!.createdAt;
      try {
        final dt = DateTime.parse(auth.profile!.createdAt).toLocal();
        memberSince =
            '${dt.year}-${dt.month.toString().padLeft(2, '0')}-${dt.day.toString().padLeft(2, '0')}';
      } catch (_) {}
      body = Container(
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(AppRadius.md),
          border: Border.all(color: AppColors.borderLight),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: const BoxDecoration(
                    color: Color(0x262D7D46),
                    shape: BoxShape.circle,
                  ),
                  alignment: Alignment.center,
                  child: const Icon(CupertinoIcons.person,
                      size: 20, color: AppColors.primary),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(auth.profile!.username,
                          style: TextStyle(
                            fontSize: AppFontSize.md * scale,
                            fontWeight: FontWeight.w700,
                            color: AppColors.textPrimary,
                          )),
                      Text('${t.auth_member_since} $memberSince',
                          style: TextStyle(
                            fontSize: AppFontSize.xs * scale,
                            color: AppColors.textTertiary,
                          )),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.md),
            CupertinoButton(
              color: AppColors.background,
              padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
              borderRadius: BorderRadius.circular(AppRadius.md),
              onPressed: () async {
                await context.read<AuthProvider>().signOut();
              },
              child: Text(t.auth_sign_out,
                  style: TextStyle(
                    fontSize: AppFontSize.sm * scale,
                    color: AppColors.textPrimary,
                  )),
            ),
          ],
        ),
      );
    } else {
      body = SizedBox(
        width: double.infinity,
        child: CupertinoButton.filled(
          onPressed: () {
            Navigator.of(context).push(
              CupertinoPageRoute(builder: (_) => const AuthScreen()),
            );
          },
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(CupertinoIcons.person,
                  size: 20, color: AppColors.textInverse),
              const SizedBox(width: AppSpacing.sm),
              Text(t.settings_sign_in),
            ],
          ),
        ),
      );
    }

    return _section(
      title: t.settings_account,
      description: t.settings_account_desc,
      scale: scale,
      child: body,
    );
  }

  // -------- Helpers --------
  Widget _section({
    required String title,
    required String description,
    required double scale,
    required Widget child,
  }) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, AppSpacing.md, AppSpacing.lg, AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title,
              style: TextStyle(
                fontSize: AppFontSize.xl * scale,
                fontWeight: FontWeight.w700,
                color: AppColors.textPrimary,
              )),
          const SizedBox(height: AppSpacing.xs),
          Text(description,
              style: TextStyle(
                fontSize: AppFontSize.sm * scale,
                color: AppColors.textSecondary,
                height: 1.4,
              )),
          const SizedBox(height: AppSpacing.md),
          child,
          const SizedBox(height: AppSpacing.md),
          Container(height: 0.5, color: AppColors.border),
        ],
      ),
    );
  }
}
