import 'package:flutter/cupertino.dart';
import 'package:provider/provider.dart';
import 'package:sentry_flutter/sentry_flutter.dart';

import 'services/supabase_client.dart';
import 'state/settings_provider.dart';
import 'state/watchlist_provider.dart';
import 'state/auth_provider.dart';
import 'theme/theme.dart';
import 'app_shell.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SupabaseService.initialize();

  await SentryFlutter.init(
    (options) {
      options.dsn =
          'https://4ce88aa19f1c4492c540187458500196@o4511277462388736.ingest.us.sentry.io/4511431449509888';
      options.sendDefaultPii = true;
    },
    appRunner: () => runApp(const AgroAmigoApp()),
  );
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
