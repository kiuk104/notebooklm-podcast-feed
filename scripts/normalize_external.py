#!/usr/bin/env python3
# external.json 의 에피소드(오디오는 GitHub Releases)를 팟캐스트 표준 음량(-16 LUFS)으로 맞춥니다.
#
# - 아직 맞추지 않은 항목(loudness != TARGET_TAG)만 처리 → 여러 번 돌려도 안전 (idempotent)
# - 이미 목표 ±1 LU 안이면 표시만 하고 건너뜀
# - 2-pass loudnorm 으로 새 파일 <원래이름>-n16.mp3 을 같은 릴리스에 올리고 url/size 를 바꿈
#   (원래 파일은 지우지 않음 — 문제가 있으면 url 만 되돌리면 됨)
#
# 필요: ffmpeg (FFMPEG 환경변수 또는 PATH), GITHUB_TOKEN, GITHUB_REPOSITORY
import json, os, re, subprocess, sys, tempfile, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "docs" / "episodes" / "external.json"
TARGET = "I=-16:TP=-1.5:LRA=11"
TARGET_TAG = "-16LUFS"
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "kiuk104/notebooklm-podcast-feed")
API = "https://api.github.com"


def gh(method, url, data=None, ctype="application/json"):
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json", "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=600) as r:
        body = r.read()
        return json.loads(body) if body else None


def measure(path):
    err = subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-i", path, "-af", f"loudnorm={TARGET}:print_format=json",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    return json.loads(err[err.rindex("{"):err.rindex("}") + 1])


def bitrate_kbps(path):
    err = subprocess.run([FFMPEG, "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Audio:.*?(\d+) kb/s", err)
    kb = int(m.group(1)) if m else 64
    return max(48, round(kb / 8) * 8)


def main() -> int:
    if not TOKEN:
        print("GITHUB_TOKEN 없음", file=sys.stderr); return 1
    data = json.loads(EXT.read_text(encoding="utf-8"))
    todo = [e for e in data.get("episodes", []) if e.get("loudness") != TARGET_TAG]
    print(f"음량 맞출 항목: {len(todo)} / {len(data.get('episodes', []))}")
    if not todo:
        return 0
    releases = {}
    changed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for e in todo:
            url = e["url"]
            m = re.match(r"https://github\.com/[^/]+/[^/]+/releases/download/([^/]+)/([^/]+)$", url)
            if not m:
                print(f"건너뜀 (릴리스 주소 아님): {url}"); continue
            tag, name = m.groups()
            src = os.path.join(tmp, name)
            try:
                urllib.request.urlretrieve(url, src)
                meas = measure(src)
            except Exception as ex:
                print(f"건너뜀 (받기/측정 실패) {name}: {ex}"); continue
            if abs(float(meas["input_i"]) + 16) <= 1.0:
                e["loudness"] = TARGET_TAG; changed += 1
                print(f"이미 맞음 {name} ({meas['input_i']} LUFS)"); continue
            stem = name[:-4] if name.endswith(".mp3") else name
            new_name = f"{stem}-n16.mp3"
            dst = os.path.join(tmp, new_name)
            af = (f"loudnorm={TARGET}:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}"
                  f":measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}"
                  f":offset={meas['target_offset']}:linear=true")
            r = subprocess.run([FFMPEG, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-i", src, "-map", "0:a",
                                "-map_metadata", "0", "-id3v2_version", "3", "-af", af, "-c:a", "libmp3lame",
                                "-b:a", f"{bitrate_kbps(src)}k", dst], capture_output=True, text=True)
            if r.returncode != 0:
                print(f"건너뜀 (변환 실패) {name}: {r.stderr[-300:]}"); continue
            # 릴리스 찾기 + 같은 이름 자산이 있으면(재실행) 지우고 올림
            if tag not in releases:
                releases[tag] = gh("GET", f"{API}/repos/{REPO}/releases/tags/{tag}")
            rel = releases[tag]
            for a in gh("GET", f"{API}/repos/{REPO}/releases/{rel['id']}/assets?per_page=100") or []:
                if a["name"] == new_name:
                    gh("DELETE", f"{API}/repos/{REPO}/releases/assets/{a['id']}")
            up = f"https://uploads.github.com/repos/{REPO}/releases/{rel['id']}/assets?name={new_name}"
            try:
                asset = gh("POST", up, data=Path(dst).read_bytes(), ctype="audio/mpeg")
            except urllib.error.HTTPError as ex:
                print(f"건너뜀 (업로드 실패) {name}: {ex.code} {ex.read()[:200]}"); continue
            e["url"] = asset["browser_download_url"]
            e["size"] = asset["size"]
            e["loudness"] = TARGET_TAG
            e["loudness_from"] = f"{float(meas['input_i']):.1f}LUFS"
            changed += 1
            print(f"맞춤 {name}: {meas['input_i']} LUFS → -16 ({new_name}, {asset['size']} bytes)")
    if changed:
        raw = EXT.read_text(encoding="utf-8")
        indent = 1 if '\n "' in raw else 2
        EXT.write_text(json.dumps(data, ensure_ascii=False, indent=indent) + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")
    print(f"바뀐 항목 {changed}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
