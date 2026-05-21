# AgroAmigo iPhone (Flutter)

Native-iOS-styled Flutter port of the React Native AgroAmigo app (`../agroamigo-app/`).
Same Supabase backend, same features, Cupertino widgets throughout.

## Architecture
- **State**: `provider` (`ChangeNotifier` providers in `lib/state/`).
- **Routing**: `go_router` with a Cupertino tab scaffold (`lib/app_shell.dart`).
- **Backend**: `supabase_flutter` (same Supabase project as the RN app).
- **Storage**: `shared_preferences` for settings + watchlist; supabase_flutter handles auth.
- **Charts**: `fl_chart`.
- **Maps**: `flutter_map` with OSM tiles (iteration target: swap to Apple Maps once CI is stable).

## Run locally (macOS)
```bash
flutter pub get
flutter run --dart-define=SUPABASE_URL=... --dart-define=SUPABASE_KEY=...
```

## Cloud build
Every push triggers `.github/workflows/agroamigo-iphone-build.yml`, which:
1. Bootstraps the iOS scaffold with `flutter create .` (no-op for files already in repo).
2. `flutter pub get`.
3. `flutter analyze`.
4. `flutter build ios --release --no-codesign --dart-define=SUPABASE_URL=... --dart-define=SUPABASE_KEY=...`.
