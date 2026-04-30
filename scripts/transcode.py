#!/usr/bin/env python3
# docs/episodes/*.{m4a,mp4} 를 mp3 로 변환. ubuntu-latest 의 native ffmpeg 사용.
# podcast.json 의 transcode 필드를 따른다 (enabled=false 면 no-op).
# 변환 성공 시 원본 삭제 — 다음 build_feed.py 가 mp3 기준으로 feed 작성.

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EPISODES_DIR = ROOT / "docs" / "episodes"
CONFIG_FILE = ROOT / "docs" / "podcast.json"

SOURCE_EXTS = {".m4a", ".mp4"}


def main() -> int:
    if not CONFIG_FILE.exists():
        return 0
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    t = cfg.get("transcode") or {}
    if not t.get("enabled"):
        return 0
    bitrate = str(t.get("bitrate", "64k"))
    channels = "1" if t.get("mono", True) else "2"

    if not EPISODES_DIR.exists():
        return 0

    converted = 0
    for src in sorted(EPISODES_DIR.iterdir()):
        if not src.is_file() or src.suffix.lower() not in SOURCE_EXTS:
            continue
        dst = src.with_suffix(".mp3")
        if dst.exists():
            # 이전 build 에서 만들어진 mp3 가 이미 있는데 원본도 남아 있는 비정상 상태.
            # 같은 이름 mp3 가 source-of-truth 라 보고 원본만 정리.
            src.unlink()
            print(f"transcode: {src.name} → mp3 already exists, removed original")
            continue

        cmd = [
            "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
            "-i", str(src),
            "-vn",
            "-map_metadata", "0",
            "-ac", channels,
            "-b:a", bitrate,
            "-codec:a", "libmp3lame",
            str(dst),
        ]
        print(f"transcode: {src.name} → {dst.name} ({bitrate}, {channels}ch)")
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"transcode failed for {src.name}:\n{r.stderr.strip()[-500:]}", file=sys.stderr)
            # 실패 시 부분 산출물 정리. 원본은 남겨서 다음 빌드에서 재시도.
            if dst.exists():
                dst.unlink()
            continue
        src.unlink()
        converted += 1

    print(f"transcode: {converted} file(s) converted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
