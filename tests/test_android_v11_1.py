import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_version_11_1_0_semver_and_same_cert():
    g = (ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    assert "?.toInt() ?: 12" in g and '?: "11.1.0"' in g
    rel = json.loads((ROOT / "app" / "android_release.json").read_text(encoding="utf-8"))
    assert rel["versionCode"] == 12 and re.fullmatch(r"\d+\.\d+\.\d+", rel["versionName"])
    assert rel["cert_sha256"] == "e775e8db9a2d1ff1e15d5572c2f5bf043c68c23b4a0721f1796278fa413a63ec"


def test_sms_raw_text_stays_on_the_phone():
    src = ROOT / "android" / "app" / "src" / "main" / "java" / "app" / "myinventory"
    receiver = (src / "SmsReceiver.kt").read_text(encoding="utf-8")
    post = receiver[receiver.index("private fun postSpend("):]
    assert 'payload.put("amount_toman", amount)' in post and 'payload.put("note", note)' in post
    assert "body" not in post.split("connection.outputStream")[0].split("val payload")[1]
    assert "SmsKeywords.cleanNote(body)" in (src / "SmsDecision.kt").read_text(encoding="utf-8")
