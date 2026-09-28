# AgroAmigo for Android

The Android app is a WebView client of the shared Azure application. Product screens, data queries and source viewers live in [apps/web](../web); native behavior is implemented in [MainActivity.java](app/src/main/java/co/agroamigo/demo/MainActivity.java).

## Behavior

- Only the configured trusted HTTPS application origin stays inside WebView; external source links open the browser.
- Native Back follows application history. Connection failures offer retry without clearing stored data.
- Foreground location is requested when the user selects GPS; denial leaves manual map placement available.
- Original documents download through Android DownloadManager. Supported JSON sharing uses the system document picker.
- Farm records, favorites and offers stay in the app's WebView storage, separately from browser storage.

Network access is required for current data. The client does not provide background location, push alerts or an offline official-price database. Native sharing support does not imply that retired farm budget editors remain in the interface.

## Build

Use Java 17 and an Android SDK with platform 35. Set `ANDROID_HOME` or the ignored `local.properties`, then run from this directory:

```sh
./gradlew assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

The checked-in Gradle wrapper supplies the build tooling. Debug APKs use debug signing; store distribution needs an owner-managed signing configuration. Generated builds are excluded from Git. The shared site's `/android` route provides installation guidance.

See [application architecture](../../docs/ARCHITECTURE.md) for the shared data and delivery boundaries.
