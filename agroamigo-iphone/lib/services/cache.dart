import 'dart:async';

/// In-memory TTL cache with in-flight de-duplication. Port of
/// `agroamigo-app/src/lib/cache.ts`.
class _Entry {
  final Object? value;
  final int expiresAtMs;
  _Entry(this.value, this.expiresAtMs);
}

class AppCache {
  AppCache._();
  static final AppCache instance = AppCache._();

  static const int defaultTtlMs = 5 * 60 * 1000;

  final Map<String, _Entry> _store = {};
  final Map<String, Future<Object?>> _inflight = {};

  T? get<T>(String key) {
    final entry = _store[key];
    if (entry == null) return null;
    if (entry.expiresAtMs <= DateTime.now().millisecondsSinceEpoch) {
      _store.remove(key);
      return null;
    }
    return entry.value as T?;
  }

  void set<T>(String key, T value, {int ttlMs = defaultTtlMs}) {
    _store[key] = _Entry(value, DateTime.now().millisecondsSinceEpoch + ttlMs);
  }

  void delete(String key) => _store.remove(key);

  void invalidatePrefix(String prefix) {
    _store.removeWhere((k, _) => k.startsWith(prefix));
  }

  void clear() {
    _store.clear();
    _inflight.clear();
  }

  Future<T> cachedCall<T>(
    String key,
    Future<T> Function() fetcher, {
    int ttlMs = defaultTtlMs,
  }) async {
    final hit = get<T>(key);
    if (hit != null) return hit;

    final pending = _inflight[key];
    if (pending != null) return await pending as T;

    final future = (() async {
      try {
        final value = await fetcher();
        set<T>(key, value, ttlMs: ttlMs);
        return value as Object?;
      } finally {
        _inflight.remove(key);
      }
    })();
    _inflight[key] = future;
    return (await future) as T;
  }
}

String cacheKey(List<Object?> parts) {
  return parts.map((p) {
    if (p == null) return '';
    return p.toString();
  }).join(':');
}
