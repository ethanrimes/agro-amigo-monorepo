import 'package:agroamigo_iphone/services/supabase_client.dart';

Future<List<Map<String, dynamic>>> getComments(
    String entityType, String entityId,
    {int limit = 50}) async {
  return SupabaseService.client
      .from('comments')
      .select('id, content, created_at, user_id, profiles(username)')
      .eq('entity_type', entityType)
      .eq('entity_id', entityId)
      .order('created_at', ascending: false)
      .limit(limit);
}

Future<List<Map<String, dynamic>>> getLatestComments({int limit = 20}) async {
  final rows = await SupabaseService.client
      .from('comments')
      .select(
          'id, content, created_at, entity_type, entity_id, user_id, profiles(username)')
      .order('created_at', ascending: false)
      .limit(limit);

  if (rows.isEmpty) return [];

  const entityTables = {
    'product': 'dim_product',
    'market': 'dim_market',
    'insumo': 'dim_insumo',
  };

  final idsByType = <String, Set<String>>{
    'product': {},
    'market': {},
    'insumo': {},
  };

  for (final r in rows) {
    final t = r['entity_type'] as String?;
    final id = r['entity_id'] as String?;
    if (t != null && id != null && idsByType.containsKey(t)) {
      idsByType[t]!.add(id);
    }
  }

  final nameMap = <String, String>{};

  await Future.wait(entityTables.entries.map((entry) async {
    final t = entry.key;
    final table = entry.value;
    final ids = idsByType[t]!.toList();
    if (ids.isEmpty) return;
    final data = await SupabaseService.client
        .from(table)
        .select('id, canonical_name')
        .in_('id', ids);
    for (final d in data) {
      nameMap['$t:${d['id']}'] = d['canonical_name'] as String? ?? '';
    }
  }));

  return rows.map((r) {
    return {
      ...r,
      'entity_name':
          nameMap['${r['entity_type']}:${r['entity_id']}'] ?? '',
    };
  }).toList();
}

Future<Map<String, dynamic>> createComment(
    String userId, String entityType, String entityId, String content) async {
  return SupabaseService.client
      .from('comments')
      .insert({
        'user_id': userId,
        'entity_type': entityType,
        'entity_id': entityId,
        'content': content.trim(),
      })
      .select('id, content, created_at, user_id, profiles(username)')
      .single();
}
