import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:agroamigo_iphone/services/supabase_client.dart';

Future<AuthResponse> signUp(
    String email, String password, String username) async {
  final existing = await SupabaseService.client
      .from('profiles')
      .select('id')
      .eq('username', username)
      .maybeSingle();
  if (existing != null) throw Exception('USERNAME_TAKEN');

  final response = await SupabaseService.client.auth
      .signUp(email: email, password: password);
  if (response.user == null) throw Exception('SIGNUP_FAILED');

  await SupabaseService.client.rpc('create_user_profile', params: {
    'p_user_id': response.user!.id,
    'p_username': username,
  });

  return response;
}

Future<AuthResponse> signIn(String email, String password) async {
  return SupabaseService.client.auth
      .signInWithPassword(email: email, password: password);
}

Future<void> signOut() async {
  await SupabaseService.client.auth.signOut();
}

Future<Session?> getSession() async {
  return SupabaseService.client.auth.currentSession;
}

Future<Map<String, dynamic>> getProfile(String userId) async {
  return SupabaseService.client
      .from('profiles')
      .select('id, username, created_at')
      .eq('id', userId)
      .single();
}

/// Returns the auth state change stream. Callers should call .listen() on it
/// and cancel the subscription when no longer needed.
Stream<AuthState> onAuthStateChange() {
  return SupabaseService.client.auth.onAuthStateChange;
}
