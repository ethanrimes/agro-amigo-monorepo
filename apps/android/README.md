# AgroAmigo Android demo

An Android client of `https://agroamigo-demo-9a04.azurewebsites.net`, sharing its Spanish interface, Azure data and PDF.js viewer. It is a hybrid app, not a separate native rewrite. Android 10+, Java 17, Gradle 8.9, Android Gradle Plugin 8.7.3 and SDK 35.

```sh
./gradlew assembleDebug lintDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

The wrapper is checked in. Set `ANDROID_HOME` or a local `local.properties` SDK path. Install platform 35 and build tools through the Android SDK manager. The demo APK uses Android's debug signing key and is suitable for direct demo installation, not a store release. A production release needs an owner-managed signing key and distribution setup.

Only the Azure app origin can navigate inside WebView. Other HTTP(S) source links open a browser. Cleartext, mixed content, file/content access, third-party cookies and geolocation permissions are disabled. Native back follows app history. A failed page load displays a retry screen without clearing stored data. Public PDFs/data files download through Android DownloadManager. The scenario export uses the system document picker, limited to a validated JSON payload from the trusted app; no JavaScript interface exposes native objects.

Personal farm/offer/scenario data stays in WebView storage and is separate from browser storage. Weather requests send the rounded location to the server/provider. Internet is required; the app does not promise offline prices or background push alerts. Keep Android System WebView updated for the PDF viewer.

To publish the installer alongside the site from the repository root:

```sh
mkdir -p apps/web/public/downloads
cp apps/android/app/build/outputs/apk/debug/app-debug.apk apps/web/public/downloads/agroamigo-demo.apk
npm run build
python3 infra/deploy.py
```

The built APK and copied download are generated artifacts, excluded from Git. `/android` provides Spanish installation instructions.

## Emulator verification

From the repository root with the app installed and an emulator booted:

```sh
ANDROID_TEST_SERIAL=emulator-5556 ANDROID_HOME=/path/to/android/sdk node apps/android/smoke.cjs
```

The explicit serial prevents targeting another running device. The check uses the deployed Azure app and verifies farm/weather, source PDF rendering, native back, offer arithmetic and device persistence.
