import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

enum WatchlistItemType { product, insumo }

class WatchlistItem {
  final String id;
  final WatchlistItemType type;
  final String name;
  final String addedAt;

  const WatchlistItem({
    required this.id,
    required this.type,
    required this.name,
    required this.addedAt,
  });

  Map<String, dynamic> toJson() => {
        'id': id,
        'type': type.name,
        'name': name,
        'addedAt': addedAt,
      };
  static WatchlistItem fromJson(Map<String, dynamic> j) => WatchlistItem(
        id: j['id'] as String,
        type: WatchlistItemType.values.firstWhere(
            (t) => t.name == j['type'],
            orElse: () => WatchlistItemType.product),
        name: j['name'] as String,
        addedAt: j['addedAt'] as String? ?? DateTime.now().toIso8601String(),
      );
}

class WatchlistProvider extends ChangeNotifier {
  static const _storageKey = 'agroamigo_watchlist';

  List<WatchlistItem> _items = [];
  bool _ready = false;

  List<WatchlistItem> get items => List.unmodifiable(_items);
  bool get ready => _ready;

  Future<void> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(_storageKey);
      if (raw != null) {
        final list = jsonDecode(raw) as List<dynamic>;
        _items = list
            .map((e) => WatchlistItem.fromJson(e as Map<String, dynamic>))
            .toList();
      }
    } catch (_) {}
    _ready = true;
    notifyListeners();
  }

  bool isWatched(String id) => _items.any((i) => i.id == id);

  Future<void> toggle(String id, WatchlistItemType type, String name) async {
    if (isWatched(id)) {
      _items = _items.where((i) => i.id != id).toList();
    } else {
      _items = [
        ..._items,
        WatchlistItem(
          id: id,
          type: type,
          name: name,
          addedAt: DateTime.now().toIso8601String(),
        ),
      ];
    }
    notifyListeners();
    await _persist();
  }

  Future<void> remove(String id) async {
    _items = _items.where((i) => i.id != id).toList();
    notifyListeners();
    await _persist();
  }

  Future<void> _persist() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_storageKey,
        jsonEncode(_items.map((i) => i.toJson()).toList()));
  }
}
