#!/usr/bin/env bash
# Build the Android APK in Docker and copy it to app/static/my-inventory.apk
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${ANDROID_APK_IMAGE:-my-inventory-android-builder}"
BASE="${ANDROID_DOCKER_BASE:-eclipse-temurin:17-jdk-jammy}"
OUT="$ROOT/app/static/my-inventory.apk"
CID="my-inventory-apk-export-$$"

cleanup() {
  docker rm -f "$CID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! docker pull "$BASE" >/dev/null 2>&1; then
  BASE="${ANDROID_DOCKER_BASE:-hub.hamdocker.ir/eclipse-temurin:17-jdk-jammy}"
  docker pull "$BASE"
fi

docker build \
  -f "$ROOT/android/Dockerfile" \
  --build-arg "BASE_IMAGE=$BASE" \
  --target builder \
  -t "$IMAGE" \
  "$ROOT"
docker create --name "$CID" "$IMAGE" /bin/true >/dev/null
docker cp "$CID:/src/android/app/build/outputs/apk/debug/app-debug.apk" "$OUT"
sha256sum "$OUT"
echo "Wrote $OUT"
