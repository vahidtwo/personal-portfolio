#!/usr/bin/env python3
"""Tiny test server for the Android update notice (QA build only).

The QA variant of the app checks http://10.0.2.2:8765/api/app-version, which from an
Android emulator is this machine's port 8765.

    python3 tools/qa_update_server.py --apk /workspace/qa-update/my-inventory-v7-test-qa.apk \
        --wrong-key-apk /workspace/qa-update/my-inventory-v7-test-wrongkey.apk --mode newer

Switch modes without restarting:  curl 'http://127.0.0.1:8765/__mode?set=wrong-sha'
Current mode:                     curl 'http://127.0.0.1:8765/__mode'

Modes
  newer          versionCode 7 (the throwaway 7.0-test APK), correct sha256  -> notice shows
  equal          versionCode 6 (same as the v6 build)                                         -> nothing
  lower          versionCode 5                                         -> nothing
  broken-json    body is not JSON                                      -> nothing
  missing-notes  no "notes" field                                      -> notice with no bullets
  slow           waits 8 s before answering (app timeout is 5 s)       -> nothing, app not delayed
  wrong-sha      sha256 of a different file                            -> download fails (state 4)
  wrong-cert     serves the APK signed with another key (correct sha)  -> download fails (state 4)
  other-host     url points at https://evil.example/...                -> nothing (URL rejected)
  http-url       url points at http://example.com/...                  -> nothing (URL rejected)
  server-error   HTTP 500                                              -> nothing
"""
import argparse
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MODES = [
    "newer", "equal", "lower", "broken-json", "missing-notes", "slow",
    "wrong-sha", "wrong-cert", "other-host", "http-url", "server-error",
]
NOTES = [
    "صفحهٔ «در حال اتصال…» به‌جای صفحهٔ سفید",
    "صفحهٔ خطای فارسی با دکمهٔ «تلاش دوباره»",
    "برگشت به آدرس پیش‌فرض، اگر آدرس اشتباهی ذخیره شده باشد",
    "رفع گیر کردن اپ در بارگذاری پشت‌سرهم",
]
CERT = "e775e8db9a2d1ff1e15d5572c2f5bf043c68c23b4a0721f1796278fa413a63ec"

state = {"mode": "newer"}
lock = threading.Lock()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_handler(args):
    apk = Path(args.apk)
    wrong = Path(args.wrong_key_apk) if args.wrong_key_apk else None

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def served_apk(self) -> Path:
            with lock:
                mode = state["mode"]
            if mode == "wrong-cert":
                if not wrong:
                    raise SystemExit("--wrong-key-apk is required for wrong-cert")
                return wrong
            return apk

        def version_json(self) -> tuple[int, bytes]:
            with lock:
                mode = state["mode"]
            if mode == "slow":
                time.sleep(8)
            if mode == "server-error":
                return 500, b'{"detail":"boom"}'
            if mode == "broken-json":
                return 200, b'{"versionCode": 7, "versionName": '
            file = self.served_apk()
            code = {"equal": 6, "lower": 5}.get(mode, args.version_code)
            url = {
                "other-host": "https://evil.example/download/my-inventory.apk",
                "http-url": "http://example.com/download/my-inventory.apk",
            }.get(mode, "/download/my-inventory.apk")
            data = {
                "versionCode": code,
                "versionName": args.version_name if code == args.version_code else f"{code}.0",
                "url": url,
                "sha256": "0" * 64 if mode == "wrong-sha" else sha256(file),
                "size_bytes": file.stat().st_size,
                "cert_sha256": CERT,
                "notes": NOTES,
                "min_required": 0,
            }
            if mode == "missing-notes":
                del data["notes"]
            return 200, json.dumps(data, ensure_ascii=False).encode("utf-8")

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/__mode":
                new = parse_qs(parsed.query).get("set", [None])[0]
                if new:
                    if new not in MODES:
                        return self._send(400, f"unknown mode; one of {MODES}".encode(), "text/plain")
                    with lock:
                        state["mode"] = new
                with lock:
                    return self._send(200, state["mode"].encode() + b"\n", "text/plain")
            if parsed.path == "/api/app-version":
                code, body = self.version_json()
                return self._send(code, body)
            if parsed.path == "/download/my-inventory.apk":
                data = self.served_apk().read_bytes()
                start = 0
                rng = self.headers.get("Range", "")
                if rng.startswith("bytes=") and rng[6:].split("-")[0].isdigit():
                    start = int(rng[6:].split("-")[0])
                    if start >= len(data):
                        return self._send(416, b"", "text/plain")
                    chunk = data[start:]
                    return self._send(206, chunk, "application/vnd.android.package-archive",
                                      {"Content-Range": f"bytes {start}-{len(data) - 1}/{len(data)}"})
                return self._send(200, data, "application/vnd.android.package-archive")
            self._send(404, b"not found", "text/plain")

        do_HEAD = do_GET

        def log_message(self, fmt, *a):
            print(f"[{state['mode']}] {self.address_string()} {fmt % a}", flush=True)

    return Handler


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apk", required=True, help="APK to offer (e.g. the v6 QA test APK)")
    p.add_argument("--wrong-key-apk", help="same version signed with another key (wrong-cert mode)")
    p.add_argument("--mode", default="newer", choices=MODES)
    p.add_argument("--version-code", type=int, default=7)
    p.add_argument("--version-name", default="7.0-test")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    state["mode"] = args.mode
    server = ThreadingHTTPServer((args.host, args.port), make_handler(args))
    print(f"QA update server on http://{args.host}:{args.port} mode={args.mode} apk={args.apk}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
