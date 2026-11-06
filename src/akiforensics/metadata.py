"""Container/metadata forensics: FLAC block inventory, MD5 integrity,
MIME mismatches, platform-tag fingerprints, decoder errors."""

from __future__ import annotations

import hashlib
import struct

import numpy as np

from . import decode

FLAC_MAGIC = b"fLaC"
BLOCK_NAMES = {0: "STREAMINFO", 1: "PADDING", 2: "APPLICATION", 3: "SEEKTABLE",
               4: "VORBIS_COMMENT", 5: "CUESHEET", 6: "PICTURE"}
KUGOU_FIELDS = ("KGHASH", "EXTEND", "QUALITY", "KRC")
_FMT_FOR_BPS = {8: "u8", 16: "s16le", 24: "s24le", 32: "s32le"}


def _parse_streaminfo(si: bytes) -> dict:
    sr = (si[10] << 12) | (si[11] << 4) | (si[12] >> 4)
    ch = ((si[12] >> 1) & 0x7) + 1
    bps = (((si[12] & 1) << 4) | (si[13] >> 4)) + 1
    ts = ((si[13] & 0x0F) << 32) | (si[14] << 24) | (si[15] << 16) | (si[16] << 8) | si[17]
    return {"sample_rate": sr, "channels": ch, "bits_per_sample": bps,
            "total_samples": ts, "md5": si[18:34].hex()}


def _parse_vorbis_comment(vc: bytes) -> dict:
    p = 0
    vlen = int.from_bytes(vc[p:p + 4], "little"); p += 4
    vendor = vc[p:p + vlen].decode("utf-8", "replace"); p += vlen
    cnt = int.from_bytes(vc[p:p + 4], "little"); p += 4
    tags: dict[str, str] = {}
    for _ in range(cnt):
        cl = int.from_bytes(vc[p:p + 4], "little"); p += 4
        entry = vc[p:p + cl].decode("utf-8", "replace"); p += cl
        if "=" in entry:
            k, v = entry.split("=", 1)
            tags[k.upper()] = v
    return {"vendor": vendor, "tags": tags}


def _picture_info(pic: bytes) -> dict:
    # FLAC PICTURE block: <32:type><32:mime_len><mime><32:desc_len><desc>...
    mime_len = int.from_bytes(pic[4:8], "big")
    mime = pic[8:8 + mime_len].decode("utf-8", "replace", errors="ignore")
    body_start = 8 + mime_len
    desc_len = int.from_bytes(pic[body_start:body_start + 4], "big")
    data_off = body_start + 4 + desc_len + 16
    magic = pic[data_off:data_off + 8]
    if magic.startswith(b"\x89PNG"):
        actual = "image/png"
    elif magic.startswith(b"\xff\xd8"):
        actual = "image/jpeg"
    else:
        actual = "unknown"
    return {"declared_mime": mime, "actual_mime": actual,
            "mime_mismatch": actual != "unknown" and mime.split(";")[0] != actual}


def verify_flac_md5(path: str, streaminfo: dict) -> dict:
    """Recompute the STREAMINFO MD5 over natively decoded PCM."""
    bps = streaminfo["bits_per_sample"]
    fmt = _FMT_FOR_BPS.get(bps)
    if fmt is None:
        return {"md5_computed": None, "md5_ok": None,
                "note": f"unsupported bit depth {bps} for MD5 check"}
    raw = decode.decode_pcm(path, sample_fmt=fmt)
    md5 = hashlib.md5(raw).hexdigest()
    return {"md5_computed": md5, "md5_ok": md5 == streaminfo["md5"]}


def analyze(path: str, probe_info: dict | None = None) -> dict:
    """Metadata leg. `probe_info` may be passed to avoid a second ffprobe run."""
    probe_info = probe_info or decode.probe(path)
    audio = next((s for s in probe_info["streams"] if s.get("codec_type") == "audio"), None)
    fmt_tags = {k.upper(): v for k, v in probe_info.get("format", {}).get("tags", {}).items()}
    out: dict = {
        "container": (probe_info.get("format", {}).get("format_name") or "?"),
        "sample_rate": int(audio["sample_rate"]) if audio else None,
        "channels": audio.get("channels") if audio else None,
        "duration_s": float(probe_info.get("format", {}).get("duration") or 0),
        "format_tags": fmt_tags,
        "flac": None,
        "platform_fingerprint": [],
        "flags": [],
    }
    if audio and audio.get("codec_name") == "flac":
        flac: dict = {"blocks": [], "vendor": None, "tags": {}}
        try:
            with open(path, "rb") as f:
                if f.read(4) != FLAC_MAGIC:
                    return out
                f.seek(4)  # skip fLaC magic
                last = False
                n_blocks = 0
                while not last and n_blocks < 128:
                    hdr = f.read(4)
                    if len(hdr) < 4:
                        break
                    last = bool(hdr[0] & 0x80)
                    btype = hdr[0] & 0x7F
                    blen = int.from_bytes(hdr[1:4], "big")
                    n_blocks += 1
                    if blen > 64_000_000:  # absurd block => corrupt/hostile
                        flac["blocks"].append(f"OVERSIZED({btype},{blen})")
                        out["flags"].append("metadata_block_oversized")
                        break
                    payload = f.read(blen)
                    if len(payload) < blen:
                        out["flags"].append("metadata_truncated")
                        break
                    flac["blocks"].append(BLOCK_NAMES.get(btype, f"type{btype}"))
                    if btype == 0 and len(payload) == 34:
                        si = _parse_streaminfo(payload)
                        flac.update(si)
                        flac["md5_check"] = verify_flac_md5(path, si)
                    elif btype == 4:
                        flac.update({k: v for k, v in _parse_vorbis_comment(payload).items()})
                    elif btype == 6:
                        flac["picture"] = _picture_info(payload)
        except OSError as e:
            out["flags"].append("metadata_read_error")
        out["flac"] = flac

        tags_u = {k.upper(): v for k, v in flac.get("tags", {}).items()}
        kugou = [k for k in KUGOU_FIELDS if k in tags_u]
        if kugou:
            out["platform_fingerprint"].append({"platform": "kugou", "fields": kugou})
        if flac.get("picture", {}).get("mime_mismatch"):
            out["flags"].append("picture_mime_mismatch")
        if flac.get("md5_check", {}).get("md5_ok") is False:
            out["flags"].append("md5_mismatch")
        if "QUALITY" in tags_u and tags_u["QUALITY"].lower() in ("flac", "lossless"):
            # platform self-declares lossless; truthfulness is spectral leg's job
            out["flags"].append("platform_quality_tag_present")
        if "SEEKTABLE" in flac["blocks"]:
            errs = decode.decode_errors(path)
            if errs:
                out["flags"].append("decoder_errors")
                out["decoder_errors"] = errs

    vendor = (out.get("flac") or {}).get("vendor")
    if vendor:
        out["vendor"] = vendor
    enc_tag = (fmt_tags.get("ENCODER") or fmt_tags.get("LAME") or
               fmt_tags.get("ENCODERSETTINGS"))
    if enc_tag:
        out["encoder_tag"] = enc_tag
    return out
