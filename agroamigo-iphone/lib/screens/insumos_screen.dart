import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import '../api/insumos_api.dart' as insumos_api;
import '../state/settings_provider.dart';
import '../theme/theme.dart';
import '../translations/dim_name.dart';
import '../translations/translations.dart';
import '../widgets/card.dart';
import 'insumo_detail_screen.dart';

/// Browse all agricultural inputs (insumos). Mirrors
/// `agroamigo-app/app/(tabs)/insumos.tsx`. Renders a grouped section list:
/// `grupo` → `subgrupo` → optional CPC sub-header → insumos.
///
/// Subgrupos are collapsible; tapping one expands the items underneath.
class InsumosScreen extends StatefulWidget {
  /// Optional initial filter — when provided via deep-link / route params,
  /// the matching grupo (and subgrupo) chip is pre-selected on first build.
  final String? grupoId;
  final String? subgrupoId;

  const InsumosScreen({super.key, this.grupoId, this.subgrupoId});

  @override
  State<InsumosScreen> createState() => _InsumosScreenState();
}

class _Section {
  final String title;
  final String grupo;
  final String grupoId;
  final bool isFirstInGrupo;
  final bool isFirstInSubgrupo;
  final String subgrupoKey;
  final int subgrupoCount;
  final String cpcCode;
  final String cpcTitle;
  final bool showCpcHeader;
  final List<Map<String, dynamic>> data;

  _Section({
    required this.title,
    required this.grupo,
    required this.grupoId,
    required this.isFirstInGrupo,
    required this.isFirstInSubgrupo,
    required this.subgrupoKey,
    required this.subgrupoCount,
    required this.cpcCode,
    required this.cpcTitle,
    required this.showCpcHeader,
    required this.data,
  });
}

class _InsumosScreenState extends State<InsumosScreen> {
  List<Map<String, dynamic>> _grupos = [];
  List<Map<String, dynamic>> _subgrupos = [];
  List<Map<String, dynamic>> _insumos = [];
  List<Map<String, dynamic>> _cpcEntries = [];

  String? _selectedGrupo;
  String? _selectedSubgrupo;
  String _search = '';
  bool _loading = true;
  final Set<String> _openSubgrupos = <String>{};

  // Infinite scroll: render N sections at a time and grow as the user scrolls.
  static const int _pageSize = 8;
  int _visibleSectionCount = _pageSize;
  final ScrollController _scrollCtrl = ScrollController();

  @override
  void initState() {
    super.initState();
    _selectedGrupo = widget.grupoId;
    _selectedSubgrupo = widget.subgrupoId;
    _scrollCtrl.addListener(_onScroll);
    _bootstrap();
  }

  @override
  void dispose() {
    _scrollCtrl.removeListener(_onScroll);
    _scrollCtrl.dispose();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    insumos_api.getInsumoGrupos().then((g) {
      if (mounted) setState(() => _grupos = g);
    }).catchError((_) {});
    insumos_api.getInsumoCpcTree().then((c) {
      if (mounted) {
        setState(() {
          _cpcEntries = c
              .whereType<Map<String, dynamic>>()
              .toList(growable: false);
        });
      }
    }).catchError((_) {});
    if (_selectedGrupo != null) {
      insumos_api.getInsumoSubgrupos(grupoId: _selectedGrupo).then((s) {
        if (mounted) setState(() => _subgrupos = s);
      }).catchError((_) {});
    }
    await _loadInsumos();
  }

  Future<void> _loadInsumos() async {
    setState(() => _loading = true);
    try {
      final data = await insumos_api.getInsumos(
        grupoId: _selectedGrupo,
        subgrupoId: _selectedSubgrupo,
        search: _search.length >= 2 ? _search : null,
        limit: 2000,
      );
      if (!mounted) return;
      setState(() {
        _insumos = data;
        _visibleSectionCount = _pageSize;
      });
    } catch (_) {
      // Swallow — caller already shows empty state on no data.
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _onScroll() {
    if (!_scrollCtrl.hasClients) return;
    final pos = _scrollCtrl.position;
    if (pos.pixels > pos.maxScrollExtent - 400) {
      final locale = context.read<SettingsProvider>().settings.locale;
      final total = _buildSections(locale).length;
      if (_visibleSectionCount < total) {
        setState(() {
          _visibleSectionCount =
              (_visibleSectionCount + _pageSize).clamp(0, total);
        });
      }
    }
  }

  void _onGrupoTap(String? id) {
    setState(() {
      _selectedGrupo = (_selectedGrupo == id) ? null : id;
      _selectedSubgrupo = null;
      _subgrupos = [];
    });
    if (_selectedGrupo != null) {
      insumos_api.getInsumoSubgrupos(grupoId: _selectedGrupo).then((s) {
        if (mounted) setState(() => _subgrupos = s);
      }).catchError((_) {});
    }
    _loadInsumos();
  }

  void _onSubgrupoTap(String? id) {
    setState(() {
      _selectedSubgrupo = (_selectedSubgrupo == id) ? null : id;
    });
    _loadInsumos();
  }

  void _toggleSubgrupo(String key) {
    setState(() {
      if (_openSubgrupos.contains(key)) {
        _openSubgrupos.remove(key);
      } else {
        _openSubgrupos.add(key);
      }
    });
  }

  List<_Section> _buildSections(AppLocale locale) {
    final cpcMap = <String, String>{};
    for (final c in _cpcEntries) {
      final code = (c['code'] ?? '').toString();
      final title = (c['title'] ?? '').toString();
      if (code.isNotEmpty) cpcMap[code] = title;
    }

    String grupoLabel(Map ins) {
      final dim = ins['dim_insumo_grupo'];
      if (dim is Map && locale == AppLocale.en) {
        final en = dim['name_en'];
        if (en is String && en.isNotEmpty) return en;
      }
      return (ins['grupo'] ?? 'Otro').toString();
    }

    String subgrupoLabel(Map ins) {
      final dim = ins['dim_insumo_subgrupo'];
      if (dim is Map && locale == AppLocale.en) {
        final en = dim['name_en'];
        if (en is String && en.isNotEmpty) return en;
      }
      return (ins['subgrupo'] ?? 'General').toString();
    }

    // grupo -> subgrupo -> cpc -> items
    final grupoMap = <String, Map<String, Object>>{};
    for (final ins in _insumos) {
      final grupoName = grupoLabel(ins);
      final grupoId = (ins['grupo_id'] ?? 'other').toString();
      final subgrupoName = subgrupoLabel(ins);
      final subgrupoId = (ins['subgrupo_id'] ?? 'general').toString();
      final cpcCode = (ins['cpc_id'] ?? '_none').toString();

      final g = grupoMap.putIfAbsent(
          grupoName,
          () => <String, Object>{
                'id': grupoId,
                'subMap': <String, Map<String, Object>>{},
              });
      final subMap = g['subMap'] as Map<String, Map<String, Object>>;
      final s = subMap.putIfAbsent(
          subgrupoName,
          () => <String, Object>{
                'id': subgrupoId,
                'cpcMap': <String, List<Map<String, dynamic>>>{},
              });
      final innerCpcMap =
          s['cpcMap'] as Map<String, List<Map<String, dynamic>>>;
      innerCpcMap.putIfAbsent(cpcCode, () => []).add(ins);
    }

    final sections = <_Section>[];
    final sortedGrupos = grupoMap.entries.toList()
      ..sort((a, b) => a.key.compareTo(b.key));
    for (final ge in sortedGrupos) {
      final grupoName = ge.key;
      final grupoId = ge.value['id'] as String;
      final subMap = ge.value['subMap'] as Map<String, Map<String, Object>>;
      var firstInGrupo = true;
      final sortedSubs = subMap.entries.toList()
        ..sort((a, b) => a.key.compareTo(b.key));
      for (final se in sortedSubs) {
        final subName = se.key;
        final innerCpcMap =
            se.value['cpcMap'] as Map<String, List<Map<String, dynamic>>>;
        final cpcEntryList = innerCpcMap.entries.toList()
          ..sort((a, b) {
            if (a.key == '_none') return 1;
            if (b.key == '_none') return -1;
            return a.key.compareTo(b.key);
          });
        final subgrupoCount =
            cpcEntryList.fold<int>(0, (n, e) => n + e.value.length);
        final subgrupoKey = '${grupoName}__$subName';
        var firstInSubgrupo = true;

        for (final ce in cpcEntryList) {
          final code = ce.key;
          final items = [...ce.value]
            ..sort((a, b) => (a['canonical_name'] ?? '')
                .toString()
                .compareTo((b['canonical_name'] ?? '').toString()));
          sections.add(_Section(
            title: subName,
            grupo: grupoName,
            grupoId: grupoId,
            isFirstInGrupo: firstInGrupo,
            isFirstInSubgrupo: firstInSubgrupo,
            subgrupoKey: subgrupoKey,
            subgrupoCount: subgrupoCount,
            cpcCode: code != '_none' ? code : '',
            cpcTitle: code != '_none' ? (cpcMap[code] ?? '') : '',
            showCpcHeader: code != '_none',
            data: items,
          ));
          firstInGrupo = false;
          firstInSubgrupo = false;
        }
      }
    }
    return sections;
  }

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<SettingsProvider>();
    final t = settings.t;
    final locale = settings.settings.locale;
    final sections = _buildSections(locale);
    final visible = sections.take(_visibleSectionCount).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg, AppSpacing.md, AppSpacing.lg, AppSpacing.sm),
          child: CupertinoSearchTextField(
            placeholder: t.inputs_search,
            onChanged: (v) {
              setState(() => _search = v);
              _loadInsumos();
            },
          ),
        ),
        _ChipRow(
          chips: [
            _ChipData(id: null, label: t.inputs_all),
            ..._grupos.map((g) => _ChipData(
                id: (g['id'] ?? '').toString(),
                label: dimDisplayName(g, locale))),
          ],
          selectedId: _selectedGrupo,
          onTap: _onGrupoTap,
        ),
        if (_subgrupos.isNotEmpty)
          _ChipRow(
            small: true,
            chips: _subgrupos
                .map((s) => _ChipData(
                    id: (s['id'] ?? '').toString(),
                    label: dimDisplayName(s, locale)))
                .toList(),
            selectedId: _selectedSubgrupo,
            onTap: _onSubgrupoTap,
          ),
        Expanded(
          child: _loading
              ? const Center(child: CupertinoActivityIndicator(radius: 14))
              : sections.isEmpty
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(AppSpacing.xl),
                        child: Text(
                          t.inputs_not_found,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            color: AppColors.textTertiary,
                            fontSize: AppFontSize.md,
                          ),
                        ),
                      ),
                    )
                  : CustomScrollView(
                      controller: _scrollCtrl,
                      slivers: [
                        SliverList.builder(
                          itemCount: visible.length,
                          itemBuilder: (context, index) =>
                              _buildSection(context, visible[index], sections),
                        ),
                        if (_visibleSectionCount < sections.length)
                          const SliverToBoxAdapter(
                            child: Padding(
                              padding: EdgeInsets.all(AppSpacing.lg),
                              child:
                                  Center(child: CupertinoActivityIndicator()),
                            ),
                          ),
                        const SliverToBoxAdapter(child: SizedBox(height: 24)),
                      ],
                    ),
        ),
      ],
    );
  }

  Widget _buildSection(
      BuildContext context, _Section section, List<_Section> all) {
    final isOpen = _openSubgrupos.contains(section.subgrupoKey);
    final children = <Widget>[];

    if (section.isFirstInGrupo) {
      final total = all
          .where((s) => s.grupo == section.grupo)
          .fold<int>(0, (n, s) => n + s.data.length);
      children.add(_GrupoHeader(name: section.grupo, count: total));
    }
    if (section.isFirstInSubgrupo) {
      children.add(_SubgrupoHeader(
        title: section.title,
        count: section.subgrupoCount,
        isOpen: isOpen,
        onTap: () => _toggleSubgrupo(section.subgrupoKey),
      ));
    }
    if (isOpen && section.showCpcHeader) {
      children.add(_CpcHeader(
        code: section.cpcCode,
        title: section.cpcTitle,
        count: section.data.length,
      ));
    }
    if (isOpen) {
      for (final item in section.data) {
        children.add(_InsumoTile(item: item));
      }
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: children,
    );
  }
}

class _ChipData {
  final String? id;
  final String label;
  const _ChipData({required this.id, required this.label});
}

class _ChipRow extends StatelessWidget {
  final List<_ChipData> chips;
  final String? selectedId;
  final ValueChanged<String?> onTap;
  final bool small;
  const _ChipRow({
    required this.chips,
    required this.selectedId,
    required this.onTap,
    this.small = false,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.xs),
      child: Wrap(
        spacing: AppSpacing.sm,
        runSpacing: AppSpacing.sm,
        children: chips.map((c) {
          final active = c.id == selectedId;
          return GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => onTap(c.id),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 120),
              padding: EdgeInsets.symmetric(
                horizontal: small ? AppSpacing.sm : AppSpacing.md,
                vertical: small ? 4 : AppSpacing.sm,
              ),
              decoration: BoxDecoration(
                color: active ? AppColors.secondary : AppColors.surface,
                borderRadius: BorderRadius.circular(AppRadius.full),
                border: Border.all(
                  color: active ? AppColors.secondary : AppColors.borderLight,
                ),
              ),
              child: Text(
                c.label,
                style: TextStyle(
                  fontSize: small ? AppFontSize.xs : AppFontSize.sm,
                  color: active
                      ? AppColors.textInverse
                      : AppColors.textSecondary,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

class _GrupoHeader extends StatelessWidget {
  final String name;
  final int count;
  const _GrupoHeader({required this.name, required this.count});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, AppSpacing.sm),
      margin: const EdgeInsets.only(top: AppSpacing.sm),
      decoration: const BoxDecoration(
        color: Color(0x12E8752A),
        border: Border(
          bottom: BorderSide(color: Color(0x33E8752A), width: 2),
        ),
      ),
      child: Row(
        children: [
          const Icon(CupertinoIcons.lab_flask,
              size: 14, color: AppColors.secondary),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              name,
              style: const TextStyle(
                fontSize: AppFontSize.lg,
                fontWeight: FontWeight.w700,
                color: AppColors.secondary,
              ),
            ),
          ),
          Text(
            '$count',
            style: const TextStyle(
                fontSize: AppFontSize.xs, color: AppColors.textTertiary),
          ),
        ],
      ),
    );
  }
}

class _SubgrupoHeader extends StatelessWidget {
  final String title;
  final int count;
  final bool isOpen;
  final VoidCallback onTap;
  const _SubgrupoHeader({
    required this.title,
    required this.count,
    required this.isOpen,
    required this.onTap,
  });
  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
        decoration: const BoxDecoration(
          border: Border(
              bottom: BorderSide(color: AppColors.borderLight, width: 0.5)),
        ),
        child: Row(
          children: [
            Expanded(
              child: Text(
                title,
                style: const TextStyle(
                  fontSize: AppFontSize.md,
                  fontWeight: FontWeight.w600,
                  color: AppColors.textPrimary,
                ),
              ),
            ),
            Text('$count',
                style: const TextStyle(
                    fontSize: AppFontSize.xs,
                    color: AppColors.textTertiary)),
            const SizedBox(width: AppSpacing.sm),
            Icon(
              isOpen ? CupertinoIcons.chevron_up : CupertinoIcons.chevron_down,
              size: 14,
              color: AppColors.textTertiary,
            ),
          ],
        ),
      ),
    );
  }
}

class _CpcHeader extends StatelessWidget {
  final String code;
  final String title;
  final int count;
  const _CpcHeader(
      {required this.code, required this.title, required this.count});
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.xl, vertical: AppSpacing.sm),
      decoration: const BoxDecoration(
        color: Color(0x082D7D46),
        border:
            Border(top: BorderSide(color: AppColors.borderLight, width: 0.5)),
      ),
      child: Row(
        children: [
          Text(code,
              style: const TextStyle(
                fontSize: AppFontSize.xs,
                fontFamily: 'Menlo',
                fontWeight: FontWeight.w600,
                color: AppColors.primary,
              )),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                  fontSize: AppFontSize.sm, color: AppColors.textSecondary),
            ),
          ),
          Text('$count',
              style: const TextStyle(
                  fontSize: AppFontSize.xs, color: AppColors.textTertiary)),
        ],
      ),
    );
  }
}

class _InsumoTile extends StatelessWidget {
  final Map<String, dynamic> item;
  const _InsumoTile({required this.item});

  @override
  Widget build(BuildContext context) {
    final id = (item['id'] ?? '').toString();
    final name = (item['canonical_name'] ?? '').toString();
    final subgrupo = (item['subgrupo'] ?? '').toString();
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.xl, 0, AppSpacing.lg, AppSpacing.xs),
      child: AppCard(
        onPressed: () {
          Navigator.of(context).push(CupertinoPageRoute(
            builder: (_) => InsumoDetailScreen(insumoId: id),
          ));
        },
        child: Row(
          children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: AppColors.secondary.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(AppRadius.md),
              ),
              child: const Icon(CupertinoIcons.lab_flask,
                  size: 18, color: AppColors.secondary),
            ),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    style: const TextStyle(
                      fontSize: AppFontSize.md,
                      fontWeight: FontWeight.w600,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  if (subgrupo.isNotEmpty)
                    Text(
                      subgrupo,
                      style: const TextStyle(
                        fontSize: AppFontSize.xs,
                        color: AppColors.textTertiary,
                      ),
                    ),
                ],
              ),
            ),
            const Icon(CupertinoIcons.chevron_forward,
                size: 16, color: AppColors.textTertiary),
          ],
        ),
      ),
    );
  }
}
