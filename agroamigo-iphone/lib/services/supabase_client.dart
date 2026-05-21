import 'package:supabase_flutter/supabase_flutter.dart';

/// Singleton wrapper. Initialize once in `main.dart` before runApp.
class SupabaseService {
  static const supabaseUrl = String.fromEnvironment('SUPABASE_URL');
  static const supabaseKey = String.fromEnvironment('SUPABASE_KEY');

  static SupabaseClient get client => Supabase.instance.client;

  static Future<void> initialize() async {
    if (supabaseUrl.isEmpty || supabaseKey.isEmpty) {
      // Allow analyzer/CI to run without secrets — runtime calls will fail
      // and the UI shows the loading state, but the build won't crash.
      await Supabase.initialize(
        url: 'https://placeholder.supabase.co',
        anonKey: 'placeholder-anon-key',
      );
      return;
    }
    await Supabase.initialize(
      url: supabaseUrl,
      anonKey: supabaseKey,
    );
  }
}
