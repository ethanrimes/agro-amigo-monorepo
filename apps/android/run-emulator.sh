#!/bin/bash
set -euo pipefail

# Dedicated AgroAmigo simulator. Do not reuse the other app's emulator-5556.
AGRO_SDK_DIR="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"
AGRO_EMULATOR="$AGRO_SDK_DIR/emulator/emulator"
AGRO_ADB="$AGRO_SDK_DIR/platform-tools/adb"

if [[ ! -x "$AGRO_EMULATOR" || ! -x "$AGRO_ADB" ]]; then
  echo "Android SDK not found. Set ANDROID_HOME to the installed SDK directory." >&2
  exit 1
fi
if [[ $# -ne 0 ]]; then
  echo "Usage: ANDROID_HOME=/path/to/sdk apps/android/run-emulator.sh" >&2
  exit 1
fi
if "$AGRO_ADB" devices | awk '$1 == "emulator-5554" { found = 1 } END { exit !found }'; then
  echo "emulator-5554 is already running. No emulator was stopped or changed." >&2
  echo "Verify its AVD name before stopping only the dedicated Pixel_9 device." >&2
  exit 1
fi
if ! "$AGRO_EMULATOR" -list-avds | awk '$0 == "Pixel_9" { found = 1 } END { exit !found }'; then
  echo "Pixel_9 AVD is not installed. Create it in Android Studio first." >&2
  exit 1
fi

# Keep userdata, avoid stale snapshots, and use the verified host graphics path.
exec "$AGRO_EMULATOR" -avd Pixel_9 -port 5554 \
  -no-snapshot-load -no-snapshot-save -no-boot-anim \
  -gpu host -feature -Vulkan \
  -dns-server "${AGRO_EMULATOR_DNS:-8.8.8.8,1.1.1.1}"
