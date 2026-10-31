#!/usr/bin/env bash
# Full test run: web (pytest-xdist) and Android unit tests (both flavors) in parallel.
# The Gradle daemon stays warm between runs; up-to-date tasks are skipped (no --rerun-tasks).
# Env: PYTHON (default python), GRADLE_ARGS (e.g. --offline), ANDROID_HOME/JAVA_HOME as for a normal build.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python}"
LOG="$(mktemp -d)"
start=$(date +%s%N)

gs="$ROOT/android/app/google-services.json"
made_gs=0
if [ ! -f "$gs" ]; then cp "$ROOT/android/app/google-services.json.example" "$gs"; made_gs=1; fi
cleanup() { [ "$made_gs" = 1 ] && rm -f "$gs"; }
trap cleanup EXIT

( cd "$ROOT/android" && ./gradlew -q ${GRADLE_ARGS:-} --daemon --parallel --build-cache \
    testDirectReleaseUnitTest testStoreReleaseUnitTest >"$LOG/android.txt" 2>&1; echo $? >"$LOG/android.rc" ) &
( cd "$ROOT" && "$PY" -m pytest -q -n auto -p no:cacheprovider >"$LOG/web.txt" 2>&1; echo $? >"$LOG/web.rc" ) &
wait

web_rc=$(cat "$LOG/web.rc"); and_rc=$(cat "$LOG/android.rc")
tail -n 3 "$LOG/web.txt"
"$PY" - "$ROOT/android/app/build/test-results" <<'PY'
import glob, sys, xml.etree.ElementTree as E
for d in sorted(glob.glob(sys.argv[1] + "/test*ReleaseUnitTest")):
    t = f = 0
    for x in glob.glob(d + "/*.xml"):
        r = E.parse(x).getroot(); t += int(r.get("tests")); f += int(r.get("failures")) + int(r.get("errors"))
    print(f"{d.rsplit('/', 1)[1]}: {t} tests, {f} failed")
PY
[ "$and_rc" = 0 ] || tail -n 30 "$LOG/android.txt"
ms=$(( ($(date +%s%N) - start) / 1000000 ))
printf 'web exit %s, android exit %s, total %d.%03ds\n' "$web_rc" "$and_rc" $((ms / 1000)) $((ms % 1000))
[ "$web_rc" = 0 ] && [ "$and_rc" = 0 ]
