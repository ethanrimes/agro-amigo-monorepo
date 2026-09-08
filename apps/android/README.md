# AgroAmigo Android demo

An Android client of `https://agroamigo-demo-9a04.azurewebsites.net`, sharing its Spanish interface, Azure data and PDF.js viewer. It is a hybrid app, not a separate native rewrite. Android 10+, Java 17, Gradle 8.9, Android Gradle Plugin 8.7.3 and SDK 35.

```sh
./gradlew assembleDebug lintDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

The wrapper is checked in. Set `ANDROID_HOME` or a local `local.properties` SDK path. Install platform 35 and build tools through the Android SDK manager. The demo APK uses Android's debug signing key and is suitable for direct demo installation, not a store release. A production release needs an owner-managed signing key and distribution setup.

Only the Azure app origin can navigate inside WebView. Other HTTP(S) source links open a browser. Cleartext, mixed content, file/content access, third-party cookies are disabled. Location is requested only when the user taps “Usar mi ubicación GPS” in the trusted Azure app. Android grants approximate or precise foreground location; denial leaves map/manual entry available. Native back follows app history. A failed page load displays a retry screen without clearing stored data. Public PDFs/data files download through Android DownloadManager. The scenario export uses the system document picker, limited to a validated JSON payload from the trusted app; no JavaScript interface exposes native objects.

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

Use the dedicated `Pixel_9` AVD on `emulator-5554`. Port 5556 belongs to another app and must not be restarted or reused by these checks. From the repository root:

```sh
ANDROID_HOME=/Users/ethan/Library/Android/sdk apps/android/run-emulator.sh
```

The launcher refuses to replace a running emulator on port 5554. If that port is occupied, first verify the AVD with `adb -s emulator-5554 emu avd name`; stop it with `adb -s emulator-5554 emu kill` only when it is the dedicated `Pixel_9` and no validation is running.

The verified underlying command is:

```sh
/Users/ethan/Library/Android/sdk/emulator/emulator -avd Pixel_9 -port 5554 \
  -no-snapshot-load -no-snapshot-save -no-boot-anim \
  -gpu host -feature -Vulkan -dns-server 8.8.8.8,1.1.1.1
```

This preserves userdata and neither loads nor writes emulator snapshots. `AGRO_EMULATOR_DNS` can override the launcher's DNS list when the local network requires different resolvers. Do not use `-wipe-data` to fix rendering problems.

This graphics configuration was verified on Apple M4/macOS, Pixel 9 Android 17/API 37 and WebView 151.0.7922.199. The active renderer was `Android Emulator OpenGL ES Translator (Apple M4)`, OpenGL ES 3.0 / Metal 90.5. The previous SwiftShader backend painted stale coffee-price blocks over other products even though DOM geometry, hit targets, and WebView CDP screenshots were correct. Disabling CSS hover transforms or adding paint containment did not fix those native pixels. Switching only the emulator renderer fixed the same deployed app, including native scroll/save/back and 48-card expansion. This result does not establish a general bug in all SwiftShader environments or physical Android devices. Keep application hardware acceleration enabled.

With the app installed and the emulator booted:

```sh
ANDROID_TEST_SERIAL=emulator-5554 ANDROID_HOME=/path/to/android/sdk node apps/android/smoke.cjs
ANDROID_TEST_SERIAL=emulator-5554 ANDROID_HOME=/path/to/android/sdk \
  ANDROID_TEST_RELEASE=REPLACE_WITH_DEPLOYED_RELEASE_ID \
  ANDROID_TEST_ARTIFACTS=artifacts/android-validation-unique-run \
  node apps/android/validate.cjs
```

The explicit serial prevents targeting another running device. The checks use the deployed Azure app and cover farm/weather, PDF and read-only Excel sources, price filters, comparisons, supply history, native back, arithmetic and device persistence. Use `ANDROID_TEST_CASES='^(26|27)-'` for focused supply/catalog checks. Case 27 captures native and WebView CDP screenshots plus DOM bounds; its geometry assertions alone do not establish a visual pass. Inspect the native screenshots before accepting a rendering fix. The harness restores original local settings and radio states, retaining a private recovery snapshot until restoration is verified.
