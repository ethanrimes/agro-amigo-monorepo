# AgroAmigo for iOS

This is the active iOS app, moved from `agroamigo-iphone`. It retains the existing TestFlight bundle ID **com.ethankallett.agroamigo.native** and its GitHub release workflow. The old Supabase screens now use the redesigned Spanish farmer/purchaser experience hosted on Azure.

`lib/main.dart` provides a WKWebView client with persistent local farm/offer/scenario data, WKWebView navigation, connection retry, source downloads through the iOS share sheet / Save to Files, and JSON scenario export. Page back buttons use the shared web interface. External HTTPS sources open in the system browser. Only the exact Azure HTTPS origin stays inside the app. There are no database credentials, arbitrary JavaScript bridges, background location access, or background push notifications in the native client. “Usar mi ubicación” requests foreground location with a Spanish permission explanation. Each farm retains its own pin and crops on the device. Prices and documents require internet access.

The product UI and calculations live in `../web`. Its evidence viewer renders original PDFs and read-only Excel workbooks retained in private Azure Blob Storage, with PostgreSQL provenance and exact page/worksheet/row links. The native source includes the Xcode project under `ios/`; only generated Pods, caches and build output are ignored. Dart and CocoaPods dependency lockfiles are tracked.

## Run and verify

Requirements: Flutter **3.44.0**, Xcode 26, CocoaPods, iOS 18+.

```sh
flutter config --no-enable-swift-package-manager
flutter pub get --enforce-lockfile
flutter analyze
flutter test
flutter run -d <iphone-or-simulator-id>
flutter drive --driver=test_driver/integration_test.dart --target=integration_test/app_test.dart -d <dedicated-simulator-id>
flutter build ios --release --no-codesign
```

The integration test uses the public Azure demo and a dedicated test simulator. It checks that the WebView reaches the bottom edge of the phone and keeps its height after navigation, with equal-width tabs above the home indicator. It creates a local Pitalito example profile, checks real PDF rendering and back navigation, and captures the native scenario share sheet for inspection in `../../artifacts`. It does not upload private offers or publish data.

Additional regression suites use the same driver:

| Target in `integration_test/` | Coverage |
| --- | --- |
| `full_validation_test.dart` | Prices, classification, filters, comparisons, PDF/Excel viewers, all bottom tabs, exact farm pin and retained supply years |
| `data_validation_test.dart` | Coffee conversions, offer arithmetic, persistence, API recovery and historical XLS sharing |
| `catalog_validation_test.dart` | Unified catalog/search/saves, exact quote identity, 1960 price history, scrolling geometry and every retained 2019/2020 supply month |

Before the full suite, set the dedicated simulator's location to the synthetic fixture `1.912345, -76.123456` using XcodeBuildMCP `set_sim_location`. At `AWAIT_NATIVE_LOCATION_PERMISSION`, accept the app's foreground location prompt and any website location prompt. The suite uses the real CoreLocation path and checks GPS provenance plus reload persistence. Reset the simulator location after the run. This fixture is test data, not the user's farm location.

The catalog suite normally uses the visible product back link after synthetic JavaScript clicks. For an actual WKWebView history check, add `--dart-define=NATIVE_CATALOG_GESTURES=true`: when the log prints `AWAIT_NATIVE_TAP`, tap the visible coffee product name through simulator UI automation; at `AWAIT_NATIVE_BACK`, perform a left-edge swipe. The suite verifies the resulting navigation and preserved settings. This optional edge-swipe check remains unverified in the current delivery; see the dated report for the native input-tool limitation. Synthetic JavaScript clicks alone do not establish the same user-activated browser history as real taps.

Use a simulator that no other task is controlling. These newer suites restore original local settings in teardown. After integration tests, rebuild and run the normal application entrypoint:

```sh
flutter build ios --simulator --debug --target lib/main.dart
flutter run --target lib/main.dart -d <dedicated-simulator-id>
```

The dated [validation report](../../docs/VALIDATION_2026-09-08.md) identifies the actual release and artifacts for each completed run; adding a test does not mean it has passed.

## TestFlight delivery

The existing workflow remains at [`../../.github/workflows/agroamigo-iphone-build.yml`](../../.github/workflows/agroamigo-iphone-build.yml), preserving its workflow run counter and app identity:

1. Every push and pull request builds from `apps/ios`, runs analysis and navigation tests, then builds unsigned for a physical iOS device.
2. A successful push to `main` (or manual workflow dispatch on `main`) creates a signed IPA and uploads it to TestFlight.
3. Other branches and pull requests do not upload. App Store Connect processing happens after the upload.

The repository variable `IOS_BUNDLE_ID_NATIVE` selects the existing bundle ID. The unchanged secret names are `APPLE_TEAM_ID`, `KEYCHAIN_PASSWORD`, `P12_PASSWORD`, `BUILD_CERTIFICATE_BASE64`, `BUILD_PROVISION_PROFILE_NATIVE_BASE64`, `APP_STORE_CONNECT_API_KEY_ID`, `APP_STORE_CONNECT_API_KEY_ISSUER_ID` and `APP_STORE_CONNECT_API_KEY_BASE64`. Credentials remain in GitHub. The version is the pubspec major/minor plus the existing workflow run number; the build number is that run number.

Web changes are hosted on Azure with `infra/deploy.py`; the iOS client loads that deployed version. A Git push triggers the iOS delivery workflow, but does not itself deploy the Azure web server. Deploy shared web changes before distributing a client that depends on them.

For the full validation suite, respond to both location dialogs on a fresh install (the iOS app prompt and the website’s “Permitir” prompt), then send a fresh simulator location fix. `--dart-define=AGRO_IOS_FARM_AND_SOURCES_ONLY=true` runs groups 16–24 as a focused continuation. The last groups cover current weather, seven-day forecasts and farm finance in table/waterfall form. See [release validation](../../docs/RELEASE_VALIDATION_2026-09-08.md) for exact device and run scope.
