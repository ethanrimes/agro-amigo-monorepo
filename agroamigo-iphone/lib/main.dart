import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';

import 'services/supabase_client.dart';
import 'state/settings_provider.dart';
import 'state/watchlist_provider.dart';
import 'state/auth_provider.dart';
import 'theme/theme.dart';
import 'app_shell.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SupabaseService.initialize();
  runApp(const AgroAmigoApp());
}

class AgroAmigoApp extends StatelessWidget {
  const AgroAmigoApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => SettingsProvider()..load()),
        ChangeNotifierProvider(create: (_) => WatchlistProvider()..load()),
        ChangeNotifierProvider(create: (_) => AuthProvider()..initialize()),
      ],
      child: CupertinoApp(
        title: 'AgroAmigo',
        theme: buildCupertinoTheme(),
        debugShowCheckedModeBanner: false,
        home: const AppShell(),
      ),
    );
  }
}
