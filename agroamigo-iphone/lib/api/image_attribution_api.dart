import 'package:agroamigo_iphone/services/supabase_client.dart';

class ImageAttribution {
  final String id;
  final String entityType; // 'product' | 'insumo'
  final String entitySlug;
  final String storagePath;
  final String sourceName;
  final String? sourceUrl;
  final String? sourceImageUrl;
  final String? license;
  final String? licenseUrl;
  final String? author;
  final String? imageTitle;
  final String fetchedAt;

  const ImageAttribution({
    required this.id,
    required this.entityType,
    required this.entitySlug,
    required this.storagePath,
    required this.sourceName,
    this.sourceUrl,
    this.sourceImageUrl,
    this.license,
    this.licenseUrl,
    this.author,
    this.imageTitle,
    required this.fetchedAt,
  });

  factory ImageAttribution.fromMap(Map<String, dynamic> m) => ImageAttribution(
        id: m['id'] as String,
        entityType: m['entity_type'] as String,
        entitySlug: m['entity_slug'] as String,
        storagePath: m['storage_path'] as String,
        sourceName: m['source_name'] as String,
        sourceUrl: m['source_url'] as String?,
        sourceImageUrl: m['source_image_url'] as String?,
        license: m['license'] as String?,
        licenseUrl: m['license_url'] as String?,
        author: m['author'] as String?,
        imageTitle: m['image_title'] as String?,
        fetchedAt: m['fetched_at'] as String,
      );
}

/// Fetch image attribution for a product or insumo by its slug.
Future<ImageAttribution?> getImageAttribution(
    String entityType, String entitySlug) async {
  try {
    final data = await SupabaseService.client
        .from('image_attributions')
        .select('*')
        .eq('entity_type', entityType)
        .eq('entity_slug', entitySlug)
        .maybeSingle();
    if (data == null) return null;
    return ImageAttribution.fromMap(data);
  } catch (e) {
    print('Error fetching image attribution: $e');
    return null;
  }
}
