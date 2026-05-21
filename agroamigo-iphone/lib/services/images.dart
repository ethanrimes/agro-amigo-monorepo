import 'supabase_client.dart';

/// Port of `agroamigo-app/src/lib/images.ts`.

const _imageBucket = 'product-images';

String _baseUrl() {
  final url = SupabaseService.supabaseUrl.isNotEmpty
      ? SupabaseService.supabaseUrl
      : 'https://placeholder.supabase.co';
  return '$url/storage/v1/object/public/$_imageBucket';
}

String slugify(String text) {
  var s = text;
  s = s.replaceAll(RegExp(r'[\u0300-\u036f]'), '');
  s = s.toLowerCase().trim();
  s = s.replaceAll(RegExp(r'[^\w\s-]'), '');
  s = s.replaceAll(RegExp(r'[\s_]+'), '_');
  s = s.replaceAll(RegExp(r'-+'), '-');
  s = s.replaceAll(RegExp(r'^[_-]+|[_-]+$'), '');
  return s;
}

const Map<String, String> _categoryImages = {
  'Frutas':
      'https://images.unsplash.com/photo-1619566636858-adf3ef46400b?w=200&h=200&fit=crop',
  'Verduras y hortalizas':
      'https://images.unsplash.com/photo-1540420773420-3366772f4999?w=200&h=200&fit=crop',
  'Tubérculos, raíces y plátanos':
      'https://images.unsplash.com/photo-1518977676601-b53f82ber63a?w=200&h=200&fit=crop',
  'Carnes':
      'https://images.unsplash.com/photo-1607623814075-e51df1bdc82f?w=200&h=200&fit=crop',
  'Pescados':
      'https://images.unsplash.com/photo-1534422298391-e4f8c172dddb?w=200&h=200&fit=crop',
  'Granos y cereales':
      'https://images.unsplash.com/photo-1586201375761-83865001e31c?w=200&h=200&fit=crop',
  'Procesados':
      'https://images.unsplash.com/photo-1473093295043-cdd812d0e601?w=200&h=200&fit=crop',
  'Lácteos y huevos':
      'https://images.unsplash.com/photo-1628088062854-d1870b4553da?w=200&h=200&fit=crop',
};

const _defaultImage =
    'https://images.unsplash.com/photo-1464226184884-fa280b87c399?w=200&h=200&fit=crop';
const _insumoFallback =
    'https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=200&h=200&fit=crop';

String getProductImageUrl({String? productName, String? categoryName}) {
  if (productName != null && productName.isNotEmpty) {
    final slug = slugify(productName);
    if (slug.length >= 2) return '${_baseUrl()}/products/$slug.jpg';
  }
  if (categoryName != null && _categoryImages.containsKey(categoryName)) {
    return _categoryImages[categoryName]!;
  }
  return _defaultImage;
}

String getCategoryImageUrl(String categoryName) {
  return _categoryImages[categoryName] ?? _defaultImage;
}

String getInsumoImageUrl({String? insumoName, String? subgrupo}) {
  if (insumoName != null && insumoName.isNotEmpty) {
    final slug = slugify(insumoName);
    if (slug.length >= 2) return '${_baseUrl()}/insumos/$slug.jpg';
  }
  if (subgrupo != null && subgrupo.isNotEmpty) {
    final slug = slugify(subgrupo);
    if (slug.length >= 2) return '${_baseUrl()}/insumos/$slug.jpg';
  }
  return _insumoFallback;
}

String getProductFallbackUrl(String? categoryName) {
  if (categoryName != null && _categoryImages.containsKey(categoryName)) {
    return _categoryImages[categoryName]!;
  }
  return _defaultImage;
}

String getInsumoFallbackUrl() => _insumoFallback;
