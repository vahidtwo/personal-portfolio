#!/usr/bin/env bash
# Build the Android release APK in Docker and copy it to app/static/my-inventory.apk
# Signing key: $MY_INVENTORY_RELEASE_DIR (default ~/.my-inventory-release) with
# keystore.properties + release.jks. Passed as BuildKit secrets, never copied into the repo.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${ANDROID_APK_IMAGE:-my-inventory-android-builder}"
BASE="${ANDROID_DOCKER_BASE:-eclipse-temurin:17-jdk-jammy}"
OUT="$ROOT/app/static/my-inventory.apk"
CID="my-inventory-apk-export-$$"
KEYDIR="${MY_INVENTORY_RELEASE_DIR:-$HOME/.my-inventory-release}"
SECRETS=()
if [ -f "$KEYDIR/keystore.properties" ] && [ -f "$KEYDIR/release.jks" ]; then
  SECRETS=(--secret "id=keystore_properties,src=$KEYDIR/keystore.properties" \
           --secret "id=release_jks,src=$KEYDIR/release.jks")
else
  echo "WARNING: no release key in $KEYDIR; the APK will be signed with a throwaway debug key" >&2
fi

cleanup() {
  docker rm -f "$CID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! docker pull "$BASE" >/dev/null 2>&1; then
  BASE="${ANDROID_DOCKER_BASE:-hub.hamdocker.ir/eclipse-temurin:17-jdk-jammy}"
  docker pull "$BASE"
fi

DOCKER_BUILDKIT=1 docker build \
  -f "$ROOT/android/Dockerfile" \
  "${SECRETS[@]}" \
  --build-arg "BASE_IMAGE=$BASE" \
  --target builder \
  -t "$IMAGE" \
  "$ROOT"
docker create --name "$CID" "$IMAGE" /bin/true >/dev/null
docker cp "$CID:/src/out/my-inventory.apk" "$OUT"
sha256sum "$OUT"
echo "Wrote $OUT"
