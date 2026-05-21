import 'dart:async';
import 'package:flutter/foundation.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import '../services/supabase_client.dart';

class Profile {
  final String id;
  final String username;
  final String createdAt;
  const Profile({required this.id, required this.username, required this.createdAt});

  static Profile fromMap(Map<String, dynamic> m) => Profile(
        id: m['id'] as String,
        username: m['username'] as String? ?? '',
        createdAt: m['created_at'] as String? ?? '',
      );
}

class AuthProvider extends ChangeNotifier {
  String? _userId;
  Profile? _profile;
  bool _loading = true;
  StreamSubscription<AuthState>? _sub;

  String? get userId => _userId;
  Profile? get profile => _profile;
  bool get loading => _loading;

  Future<void> initialize() async {
    try {
      final session = SupabaseService.client.auth.currentSession;
      _userId = session?.user.id;
      if (_userId != null) await _loadProfile(_userId!);
    } catch (_) {}
    _loading = false;
    notifyListeners();

    _sub = SupabaseService.client.auth.onAuthStateChange.listen((event) {
      final uid = event.session?.user.id;
      _userId = uid;
      if (uid != null) {
        _loadProfile(uid);
      } else {
        _profile = null;
        notifyListeners();
      }
    });
  }

  Future<void> _loadProfile(String uid) async {
    try {
      final data = await SupabaseService.client
          .from('profiles')
          .select('id, username, created_at')
          .eq('id', uid)
          .single();
      _profile = Profile.fromMap(data);
    } catch (_) {
      _profile = null;
    }
    notifyListeners();
  }

  Future<void> refreshProfile() async {
    if (_userId != null) await _loadProfile(_userId!);
  }

  Future<void> signOut() async {
    await SupabaseService.client.auth.signOut();
    _userId = null;
    _profile = null;
    notifyListeners();
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }
}
