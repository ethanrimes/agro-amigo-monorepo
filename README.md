# AgroAmigo

A Spanish-language agricultural planning demo for Colombian farmers and purchasers. The redesigned app combines dated market references, farm planning, crop budgets, private offer comparisons, and source documents stored in Azure PostgreSQL.

- Web: https://agroamigo-demo-9a04.azurewebsites.net
- Android installer: https://agroamigo-demo-9a04.azurewebsites.net/android
- Start with **Mi finca**, or choose **Explorar ejemplo en Pitalito**.

## Repository

| Folder | Purpose |
|---|---|
| `apps/web` | Next.js application, server APIs, PDF viewer, browser tests |
| `apps/android` | Installable Android client for the same Azure application |
| `apps/ios` | Flutter iOS client, Xcode project and existing TestFlight app identity |
| `pipelines/demo` | Recent DANE, FNC and SFC observations; date-window guards |
| `pipelines/planning` | Historical references, crop/soil/suitability data, documents and methodology |
| `data` | Original municipal reference files |
| `infra` | Azure provisioning and verified deployment |
| `docs` | Architecture, data-source research and verification notes |

The active Flutter iOS app moved from `agroamigo-iphone` to `apps/ios`; its TestFlight workflow remains `.github/workflows/agroamigo-iphone-build.yml`. The old Expo and second web prototypes, unused shared Supabase package, legacy Supabase ingestion/migrations and 20 unreachable web modules were removed. Their prior versions remain in Git history. One npm lockfile manages the web workspace; iOS has its own Dart and CocoaPods lockfiles. Generated caches, build output, APK copies and credentials are ignored.

## Run the web app

Requires Node 22. Use `apps/web/.env.example` to create `apps/web/.env.local` with the server-side Azure `DATABASE_URL`. Never expose the connection through a `NEXT_PUBLIC_` variable.

```sh
npm ci
npm run dev
```

Development defaults to http://localhost:3000. To test on port 3002:

```sh
npm run dev -- --hostname 127.0.0.1 --port 3002
```

## Data and deployment

Read [the pipeline instructions](pipelines/README.md) and [Azure operations](infra/README.md). Current prices and input observations retain only the latest 12 months. Five complete years are stored separately for seasonality; older technical references preserve their publication periods.

```sh
npm run build
python3 infra/deploy.py
```

The deployment verifies a unique release file and database health. Source documents are immutable byte records in PostgreSQL; links inside the app open their exact document or dataset records.

## Android

The Android app uses the shared web experience with native back navigation, download handling, a connection-retry screen, and local device storage. It requires Android 10+ and an updated Android System WebView. This is a directly installable demo APK, not a Google Play release.

```sh
cd apps/android
# Java 17 and an Android SDK containing platform 35 are required.
./gradlew assembleDebug lintDebug
```

APK: `apps/android/app/build/outputs/apk/debug/app-debug.apk`.
To publish the installer with the web app, copy it to `apps/web/public/downloads/agroamigo-demo.apk` before deploying. See [Android details](apps/android/README.md).

## iOS and TestFlight

The iOS app lives in [apps/ios](apps/ios). It displays the same Azure app through WKWebView, with native back navigation, document sharing / Save to Files, scenario export, connection recovery and persistent device storage. It supports iOS 18+ and retains the existing `com.ethankallett.agroamigo.native` TestFlight identity.

```sh
cd apps/ios
# Flutter 3.44.0, Xcode 26 and CocoaPods are required.
flutter config --no-enable-swift-package-manager
flutter pub get --enforce-lockfile
flutter run -d <iphone-or-simulator-id>
```

Every push runs the iOS build workflow. A successful push to `main` then signs and uploads an IPA to TestFlight using the existing GitHub secrets; pull requests and other branches only build. Web hosting remains on Azure, deployed using `infra/deploy.py`. See [iOS build and release details](apps/ios/README.md).

## Verification

```sh
npm run build
npx playwright install chromium
npm run test:e2e
# Or run the same browser checks against an existing deployment:
PLAYWRIGHT_BASE_URL=https://agroamigo-demo-9a04.azurewebsites.net npm run test:e2e
.venv/bin/python pipelines/demo/verify_database.py
.venv/bin/python pipelines/planning/verify.py
```

Browser tests cover desktop/mobile workflows, arithmetic, source integrity, PDF pagination, persistence and unavailable data. GitHub Actions builds web, Android and iOS, runs Android lint and checks iOS navigation rules; live database tests require a configured environment.

The demo is a dated reference snapshot, with live weather requests. Crop scenarios are transparent planning assumptions, not validated farm-specific forecasts. See [coverage and limitations](docs/DATA_SOURCES.md).
