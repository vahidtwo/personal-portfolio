import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_version_11_1_0_semver_and_same_cert():
    # 12.0.0 (13) supersedes 11.1.0 (12); the cert and semver rules stay.
    rel = json.loads((ROOT / "app" / "android_release.json").read_text(encoding="utf-8"))
    assert rel["versionCode"] >= 12 and re.fullmatch(r"\d+\.\d+\.\d+", rel["versionName"])
    assert rel["cert_sha256"] == "e775e8db9a2d1ff1e15d5572c2f5bf043c68c23b4a0721f1796278fa413a63ec"


def test_sms_raw_text_stays_on_the_phone():
    src = ROOT / "android" / "app" / "src" / "main" / "java" / "app" / "myinventory"
    receiver = (src / "SmsReceiver.kt").read_text(encoding="utf-8")
    queue = (src / "SmsQueue.kt").read_text(encoding="utf-8")
    payload = queue[queue.index("fun payload("):queue.index("// ---- storage")]
    assert '.put("amount_toman", e.amountToman).put("note", e.note)' in payload
    assert "body" not in payload
    assert "SmsQueue.Entry(amount, note, idem," in receiver
    entry = queue[queue.index("data class Entry("):].split("\n")[0]
    assert "body" not in entry and "sender" not in entry
    assert "SmsKeywords.cleanNote(body)" in (src / "SmsDecision.kt").read_text(encoding="utf-8")
