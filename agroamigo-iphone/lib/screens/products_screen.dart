import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import '../api/products_api.dart';
import '../services/cache.dart';
import '../state/settings_provider.dart';
import '../theme/theme.dart';
import '../translations/dim_name.dart';
import '../translations/translations.dart';
import '../widgets/card.dart';
import '../widgets/product_image.dart';
import '../widgets/search_bar.dart';
import 'product_detail_screen.dart';

/// Port of `agroamigo-app/app/(tabs)/products.tsx`.
///
/// Adds Cupertino-flavoured infinite scroll (load 50 at a time) on top of
/// the original RN `SectionList`. Honours an optional [categoryId] route
/// param so Home tiles can pre-filter the list.
class ProductsScreen extends StatefulWidget {
  final String? categoryId;
  const ProductsScreen({super.key, this.categoryId});

  @override
  State<ProductsScreen> createState() => _ProductsScreenState();
}

class _ProductsScreenState extends State<ProductsScreen> {
  static const int _pageSize = 50;

  final TextEditingController _searchCtl = TextEditingController();
  final ScrollController _scrollCtl = ScrollController();

  List<dynamic> _products = const [];
  List<dynamic> _categories = const [];
  List<dynamic> _subcategories = const [];

  String? _selectedCategoryId;
  String? _selectedSubcategoryId;
  String _search = '';

  bool _loading = true;
  bool _loadingMore = false;
  bool _hasMore = true;
  int _limit = _pageSize;

  @override
  void initState() {
    super.initState();
    _selectedCategoryId = widget.categoryId;
    _scrollCtl.addListener(_onScroll);
    _bootstrap();
  }

  @override
  void dispose() {
    _scrollCtl.removeListener(_onScroll);
    _scrollCtl.dispose();
    _searchCtl.dispose();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    final cats = await AppCache.instance.cachedCall<List<dynamic>>(
      'products:categories',
      () async => (await getCategories()) ?? const <dynamic>[],
    );
    if (!mounted) return;
    setState(() => _categories = cats);
    if (_selectedCategoryId != null) {
      _loadSubcategories(_selectedCategoryId!);
    }
    await _loadProducts(reset: true);
  }

  Future<void> _loadSubcategories(String categoryId) async {
    try {
      final subs = await getSubcategories(categoryId: categoryId);
      if (!mounted) return;
      setState(() => _subcategories = subs ?? const []);
    } catch (_) {
      if (!mounted) return;
      setState(() => _subcategories = const []);
    }
  }

  Future<void> _loadProducts({bool reset = false}) async {
    if (reset) {
      setState(() {
        _loading = true;
        _limit = _pageSize;
        _hasMore = true;
      });
    } else {
      if (_loadingMore || !_hasMore) return;
      setState(() => _loadingMore = true);
      _limit += _pageSize;
    }

    try {
      final search = _search.length >= 2 ? _search : null;
      final data = await getProducts(
        categoryId: _selectedCategoryId,
        subcategoryId: _selectedSubcategoryId,
        search: search,
        limit: _limit,
      );
      final list = data ?? const <dynamic>[];
      if (!mounted) return;
      setState(() {
        _products = list;
        _hasMore = list.length >= _limit;
      });
    } catch (e) {
      // ignore: avoid_print
      print('Error loading products: $e');
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
          _loadingMore = false;
        });
      }
    }
  }

  void _onScroll() {
    if (_scrollCtl.position.pixels >=
        _scrollCtl.position.maxScrollExtent - 240) {
      _loadProducts();
    }
  }

  void _onSearchChanged(String v) {
    setState(() => _search = v);
    _loadProducts(reset: true);
  }

  void _selectCategory(String? id) {
    if (id == _selectedCategoryId) return;
    setState(() {
      _selectedCategoryId = id;
      _selectedSubcategoryId = null;
      _subcategories = const [];
    });
    if (id != null) _loadSubcategories(id);
    _loadProducts(reset: true);
  }

  void _selectSubcategory(String? id) {
    if (id == _selectedSubcategoryId) return;
    setState(() => _selectedSubcategoryId = id);
    _loadProducts(reset: true);
  }

  String? _categoryName(dynamic product, AppLocale locale) {
    final sub = product is Map ? product['dim_subcategory'] : null;
    final cat = sub is Map ? sub['dim_category'] : null;
    final name = dimDisplayName(cat as Map?, locale);
    return name.isEmpty ? null : name;
  }

  @override
  Widget build(BuildContext context) {
    final settings = context.watch<SettingsProvider>();
    final t = settings.t;
    final locale = settings.settings.locale;

    return Container(
      color: AppColors.background,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg,
              AppSpacing.md,
              AppSpacing.lg,
              AppSpacing.sm,
            ),
            child: AppSearchBar(
              controller: _searchCtl,
              placeholder: t.products_search,
              onChanged: _onSearchChanged,
            ),
          ),
          _buildCategoryChips(t.products_all, locale),
          if (_selectedCategoryId != null && _subcategories.isNotEmpty)
            _buildSubcategoryChips(t.products_all, locale),
          Expanded(
            child: _loading
                ? const Center(
                    child: Padding(
                      padding: EdgeInsets.only(top: 40),
                      child: CupertinoActivityIndicator(radius: 14),
                    ),
                  )
                : _buildList(t, locale),
          ),
        ],
      ),
    );
  }

  Widget _buildCategoryChips(String allLabel, AppLocale locale) {
    return SizedBox(
      height: 38,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
        itemCount: _categories.length + 1,
        separatorBuilder: (_, __) => const SizedBox(width: AppSpacing.sm),
        itemBuilder: (context, i) {
          if (i == 0) {
            return _Chip(
              label: allLabel,
              active: _selectedCategoryId == null,
              onTap: () => _selectCategory(null),
            );
          }
          final c = _categories[i - 1] as Map;
          final id = c['id'] as String?;
          return _Chip(
            label: dimDisplayName(c, locale),
            active: _selectedCategoryId == id,
            onTap: () => _selectCategory(id),
          );
        },
      ),
    );
  }

  Widget _buildSubcategoryChips(String allLabel, AppLocale locale) {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.xs),
      child: SizedBox(
        height: 34,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          itemCount: _subcategories.length + 1,
          separatorBuilder: (_, __) => const SizedBox(width: AppSpacing.sm),
          itemBuilder: (context, i) {
            if (i == 0) {
              return _Chip(
                label: allLabel,
                active: _selectedSubcategoryId == null,
                small: true,
                onTap: () => _selectSubcategory(null),
              );
            }
            final s = _subcategories[i - 1] as Map;
            final id = s['id'] as String?;
            return _Chip(
              label: dimDisplayName(s, locale),
              active: _selectedSubcategoryId == id,
              small: true,
              onTap: () => _selectSubcategory(id),
            );
          },
        ),
      ),
    );
  }

  Widget _buildList(dynamic t, AppLocale locale) {
    if (_products.isEmpty) {
      return Padding(
        padding: const EdgeInsets.only(top: 40),
        child: Text(
          t.products_not_found,
          textAlign: TextAlign.center,
          style: const TextStyle(
            fontSize: AppFontSize.md,
            color: AppColors.textTertiary,
          ),
        ),
      );
    }
    return CustomScrollView(
      controller: _scrollCtl,
      slivers: [
        CupertinoSliverRefreshControl(
          onRefresh: () => _loadProducts(reset: true),
        ),
        SliverPadding(
          padding: const EdgeInsets.only(bottom: 24),
          sliver: SliverList.builder(
            itemCount: _products.length + (_loadingMore ? 1 : 0),
            itemBuilder: (context, index) {
              if (index >= _products.length) {
                return const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16),
                  child: Center(child: CupertinoActivityIndicator()),
                );
              }
              return _buildProductRow(_products[index], locale);
            },
          ),
        ),
      ],
    );
  }

  Widget _buildProductRow(dynamic p, AppLocale locale) {
    final name = (p['canonical_name'] as String?) ?? '';
    final categoryName = _categoryName(p, locale);
    final id = p['id'] as String?;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        0,
        AppSpacing.lg,
        AppSpacing.xs,
      ),
      child: AppCard(
        onTap: id == null
            ? null
            : () {
                Navigator.of(context).push(
                  CupertinoPageRoute(
                    builder: (_) => ProductDetailScreen(productId: id),
                  ),
                );
              },
        child: Row(
          children: [
            ProductImage(
              productName: name,
              categoryName: categoryName,
              size: 44,
              radius: AppRadius.md,
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
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (categoryName != null && categoryName.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text(
                        categoryName,
                        style: const TextStyle(
                          fontSize: AppFontSize.xs,
                          color: AppColors.textTertiary,
                        ),
                      ),
                    ),
                ],
              ),
            ),
            const Icon(
              CupertinoIcons.chevron_right,
              size: 18,
              color: AppColors.textTertiary,
            ),
          ],
        ),
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  final String label;
  final bool active;
  final bool small;
  final VoidCallback onTap;
  const _Chip({
    required this.label,
    required this.active,
    required this.onTap,
    this.small = false,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        alignment: Alignment.center,
        padding: EdgeInsets.symmetric(
          horizontal: small ? AppSpacing.sm : AppSpacing.md,
          vertical: small ? AppSpacing.xs : AppSpacing.sm,
        ),
        decoration: BoxDecoration(
          color: active ? AppColors.primary : AppColors.surface,
          borderRadius: BorderRadius.circular(AppRadius.full),
          border: Border.all(
            color: active ? AppColors.primary : AppColors.borderLight,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: small ? AppFontSize.xs : AppFontSize.sm,
            fontWeight: FontWeight.w500,
            color: active ? AppColors.textInverse : AppColors.textSecondary,
          ),
        ),
      ),
    );
  }
}
