# feed-builder — GitHub Actions 워크플로 example

익스텐션의 **RSS feed 생성 방식 = "GitHub Actions 에 위임"** (default) 모드를 작동시키는 표준 한 벌. 본인 RSS 호스팅 repo 에 그대로 복사하면 audio 가 push 될 때마다 `docs/feed.xml` 이 자동으로 다시 생성되고 commit 됩니다.

## 디렉토리 구조

이 폴더 안의 파일 4개를 본인 repo (`kiuk104/my-notebooklm-podcast` 같은 익스텐션 옵션의 repo) 에 같은 경로로 복사:

```
your-repo/
├─ .github/
│  └─ workflows/
│     └─ build-feed.yml         # 워크플로 정의
├─ scripts/
│  └─ build_feed.py             # feed.xml 생성 스크립트 (Python 표준 라이브러리만)
└─ docs/
   ├─ podcast.json              # 팟캐스트 메타 (제목/설명/오너 등)
   └─ episodes/                 # 익스텐션이 PUT 한 m4a/mp3 가 쌓이는 곳
```

## 셋업 순서

1. **본인 repo 가 이미 있고 `Settings → Pages` 가 `main` / `/docs` 로 활성화되어 있는지 확인** (도움말 §2-1).
2. **`docs/podcast.json` 을 본인 정보로 수정** — 적어도 `title`, `ownerName`, `ownerEmail` 은 채우는 게 좋습니다. `image` 는 외부 URL (1400x1400 이상 JPG/PNG, 일부 팟캐스트 앱 검색 등록 시 필수).
3. **워크플로 / 스크립트 파일을 복사** — 위 4개 파일을 본인 repo 에 같은 경로로 PR 또는 직접 push.
4. **첫 빌드 트리거** — Actions 탭에서 `Build podcast feed` workflow 를 [Run workflow] 로 한 번 실행 (또는 아무 commit 한 번이면 됨). 성공하면 `docs/feed.xml` 이 자동으로 생성/commit 됩니다.
5. **RSS URL 확인** — `https://<사용자>.github.io/<repo>/feed.xml` 가 200 으로 떨어지면 끝. 팟캐스트 앱에 등록.

이 후로는 익스텐션이 audio 를 `docs/episodes/` 에 PUT 할 때마다 워크플로가 자동 트리거되어 feed 가 갱신됩니다.

## 동작 원리

- **트리거**: `docs/episodes/**`, `docs/podcast.json`, `scripts/build_feed.py`, 워크플로 자체에 변경이 있는 push 만 빌드 (audio 가 들어올 때 + 메타가 바뀔 때).
- **파일명 파싱**: `YYYYMMDD__노트북-슬러그__제목-슬러그.{m4a|mp3|mp4}` 규약으로 파싱 → RSS item 의 pubDate / title / description 으로 매핑. 익스텐션의 [src/background.js] `buildFilename` 과 정확히 같은 형식이어야 합니다.
- **enclosure URL**: `${BASE_URL}episodes/<filename>` (BASE_URL 은 워크플로의 `env` 에서 GitHub Pages URL 로 자동 조립). `podcast.json` 의 `baseUrl` 을 명시하면 그 값이 우선 (custom domain 등을 위해).
- **변경 없으면 commit 스킵** — feed 내용이 똑같으면 빈 commit 안 만듭니다.

## Transcode (m4a → mp3)

NotebookLM 의 m4a 는 256k stereo 라 한 시간에 ~22MB 입니다. 음성개요는 사람 목소리 위주라 64k mono mp3 (~5MB) 로도 충분히 들립니다 — repo 1GB 한도가 4배 늘어나는 효과.

`docs/podcast.json` 의 `transcode` 필드로 켭니다:

```json
"transcode": {
  "enabled": true,
  "bitrate": "64k",
  "mono": true
}
```

워크플로의 `Transcode m4a/mp4 → mp3` step 이 `docs/episodes/` 안의 m4a/mp4 를 같은 이름의 mp3 로 변환하고 원본을 삭제합니다. 이미 있는 mp3 는 건드리지 않음. 변환 자체는 `ubuntu-latest` 의 native ffmpeg (`libmp3lame` 포함) 가 처리해서 1시간짜리 audio 도 5–10초.

- `bitrate`: 문자열 (`"64k"`, `"96k"`, `"128k"` 등). 음성 위주면 `64k`, 음악/효과음 비중이 높으면 `96k` 이상 권장.
- `mono`: true 면 `-ac 1` 로 다운믹스. NotebookLM 음성개요는 기본적으로 mono 라 stereo 유지의 의미가 작음.
- 미설정/`enabled: false` 면 변환 없이 m4a 그대로 유지.

변환 실패 시 (드물지만 깨진 m4a 등) 원본은 남기고 다음 빌드에서 재시도. 실패 로그는 Actions 의 step output 에 남습니다.

## 보관 정책 (rolling window)

`docs/podcast.json` 의 `retention` 필드로 repo 용량을 통제할 수 있습니다. 두 RSS 모드 (워크플로 위임 / 익스텐션 직접) 모두 같은 정책을 따릅니다.

```json
"retention": {
  "maxItems": 50,
  "maxAgeDays": 365
}
```

- `maxItems`: 최근 N 개만 유지. 그보다 오래된 episode 는 build 시점에 자동 삭제.
- `maxAgeDays`: 오늘로부터 N 일 이내 episode 만 유지.
- 둘 다 설정하면 둘 다 통과해야 keep — 더 짧은 정책이 효과적.
- 한 쪽만 쓰려면 다른 쪽을 빼거나 `0` 으로. 필드 자체를 제거하면 정리 비활성.

워크플로 모드는 build 시 파일 시스템에서 unlink + `git add -A docs/...` → 다음 commit 에 같이 들어갑니다. 익스텐션 모드는 audio push 직후 GitHub Contents API DELETE 로 같은 동작.

NotebookLM 의 카드 자체를 지우는 것과는 무관합니다 — repo 의 파일만 정리. 같은 카드를 다시 받기로 누르면 (NotebookLM 에 살아 있는 한) 다시 push 됩니다.

## 커스터마이즈

- **다른 정렬 / 그룹핑** — `build_feed.py` 의 `collect_episodes()` 정렬 키를 변경.
- **에피소드 description 강화** — 현재는 title 을 그대로 description 으로 쓰지만, NotebookLM 요약 / 첫 단락 같은 걸 넣고 싶다면 별도 메타 파일 (예: `docs/episodes/<basename>.txt`) 을 같이 push 해서 build 시 읽어 inject.
- **duration 표시** — `itunes:duration` 추가하려면 `apt-get install -y ffmpeg` 후 `ffprobe` 로 길이 추출. 첫 빌드 시간이 길어지므로 episodes 가 많아진 뒤에 켜는 걸 권장.

## 트러블슈팅

| 증상 | 점검 |
|---|---|
| Actions 가 안 돌아감 | repo 의 Actions 가 활성화되어 있는지 (`Settings → Actions → General`). private repo 에 Actions 분 한도가 있는지. |
| `Permission denied` push | 워크플로의 `permissions: contents: write` 가 빠지지 않았는지. 신규 repo 는 `Settings → Actions → General → Workflow permissions` 가 "Read and write" 로 되어 있어야 함. |
| `baseUrl not set` | `docs/podcast.json` 에 baseUrl 명시하거나, 워크플로의 `BASE_URL` env 변수가 비어 있지 않은지 확인. |
| 팟캐스트 앱에 안 잡힘 | RSS URL 이 200 OK 인지 직접 브라우저로 확인 → `<itunes:image>` 가 비어 있거나 너무 작은 이미지면 일부 앱이 거절. |
