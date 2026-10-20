"""Version and size of the Android APK actually served at /download/my-inventory.apk.

The version is read from the APK's own (binary) AndroidManifest.xml, so it always matches the file on the
server (the android/ sources are not in the Docker image). Any parsing problem just hides the version.
"""

from __future__ import annotations

import struct
import zipfile
from functools import lru_cache
from pathlib import Path

from app.formatting import format_number, persian_digits

_RES_STRING_POOL = 0x0001
_RES_XML_START_ELEMENT = 0x0102
_TYPE_STRING = 0x03


def _string_pool(data: bytes, off: int) -> list[str]:
    _type, header_size, _size, count, _styles, flags, strings_start, _styles_start = struct.unpack_from("<HHIIIIII", data, off)
    utf8 = bool(flags & (1 << 8))
    offsets = struct.unpack_from(f"<{count}I", data, off + header_size)
    base = off + strings_start
    out = []
    for o in offsets:
        p = base + o
        if utf8:
            n = data[p]; p += 2 if n & 0x80 else 1  # utf-16 length (skipped)
            n = data[p]
            if n & 0x80:
                n = ((n & 0x7F) << 8) | data[p + 1]; p += 2
            else:
                p += 1
            out.append(data[p:p + n].decode("utf-8", "replace"))
        else:
            n = struct.unpack_from("<H", data, p)[0]; p += 2
            if n & 0x8000:
                n = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", data, p)[0]; p += 2
            out.append(data[p:p + 2 * n].decode("utf-16-le", "replace"))
    return out


def manifest_version_name(data: bytes) -> str | None:
    """versionName from a compiled AndroidManifest.xml."""
    off = struct.unpack_from("<HHI", data, 0)[1]  # skip the XML chunk header
    strings: list[str] = []
    while off + 8 <= len(data):
        ctype, header_size, size = struct.unpack_from("<HHI", data, off)
        if size <= 0:
            break
        if ctype == _RES_STRING_POOL:
            strings = _string_pool(data, off)
        elif ctype == _RES_XML_START_ELEMENT and strings:
            name_idx = struct.unpack_from("<I", data, off + 20)[0]
            if strings[name_idx] == "manifest":
                attr_start, attr_size, attr_count = struct.unpack_from("<HHH", data, off + 24)
                a = off + 16 + attr_start
                for i in range(attr_count):
                    _ns, aname, raw, _vsize, _res0, dtype, value = struct.unpack_from("<IIIHBBI", data, a + i * attr_size)
                    if strings[aname] == "versionName":
                        if raw != 0xFFFFFFFF:
                            return strings[raw]
                        if dtype == _TYPE_STRING:
                            return strings[value]
                return None
        off += size
    return None


@lru_cache(maxsize=4)
def _read_version(path: str, _mtime: float, _size: int) -> str | None:
    try:
        with zipfile.ZipFile(path) as zf:
            return manifest_version_name(zf.read("AndroidManifest.xml"))
    except Exception:
        return None


def apk_info(path: Path) -> dict | None:
    """{'size': '۴ مگابایت', 'version': '۳٫۰' or None}, or None when the APK is not on the server."""
    try:
        st = path.stat()
    except OSError:
        return None
    mb = st.st_size / (1024 * 1024)
    version = _read_version(str(path), st.st_mtime, st.st_size)
    return {
        "size": f"{format_number(mb, 0 if mb >= 1 else 1)} مگابایت",
        "version": persian_digits(version).replace(".", "٫") if version else None,
    }
