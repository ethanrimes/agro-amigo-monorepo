# AgroAmigo for iOS

The iOS app uses Flutter and WKWebView to load the shared Azure interface. [lib/main.dart](lib/main.dart) owns the native shell; product behavior and APIs live in [apps/web](../web).

## Behavior

The client provides safe-area layout, native navigation, connection retry, foreground location permissions and source sharing through the iOS share sheet. External HTTPS sources open in the system browser; only the trusted application origin remains inside WKWebView.

Farm records, favorites and private offers persist in the app's WebView storage. They are not synchronized with Safari or another device. Existing farm/scenario bytes remain stored while Mi finca presents read-only references. Source requests require connectivity.

## Local setup

Use Flutter 3.44 or later, Xcode and CocoaPods. From this directory:

```sh
flutter config --no-enable-swift-package-manager
flutter pub get --enforce-lockfile
flutter run -d <device-id>
```

The supported iOS deployment target is defined in the Xcode project. Physical-device builds require appropriate signing; simulator builds do not establish store distribution.

## Delivery structure

The [iOS workflow](../../.github/workflows/agroamigo-iphone-build.yml) builds the native application and supports signed TestFlight uploads from the configured main-branch workflow. Signing material is supplied through repository secrets. App Store processing is separate from uploading a build.

Shared web changes are deployed independently to Azure; native shell changes require a new client build. See [architecture](../../docs/ARCHITECTURE.md) and [infrastructure](../../infra/README.md).
