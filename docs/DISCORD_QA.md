# Discord QA 연결

대상은 `코디세이해커톤2026_수건돌리기` 서버의 [#qa 채널](https://discord.com/channels/1561765886778413206/1566058637904846898)이다. `scripts/discord_qa.py`가 공식 Discord REST API의 GET으로 조회하고, 완료 표시 도구는 해당 원문의 ✅ 반응만 PUT으로 추가한다. 다른 서버나 채널은 조회할 수 없고, 스레드는 부모 채널이 #qa인 경우만 허용한다.

## 로컬 설정

전용 Python 환경은 `.venv/discord-qa`이며, 의존성은 `tools/discord_qa/requirements.txt`로 분리했다. 사이트 서버의 의존성이나 배포 환경에는 추가하지 않는다. 도구는 Python 3.11 이상이 필요하다.

[ToonPick QA Bot 설정](https://discord.com/developers/applications/1566067698880745542/bot)에서 Message Content Intent를 활성화한다. Bot 토큰을 `.env.discord.local`의 `DISCORD_BOT_TOKEN=` 뒤에 입력한다. OAuth2 Client Secret은 사용하지 않는다. 프로세스 환경변수 `DISCORD_BOT_TOKEN`이 있으면 파일보다 우선한다.

토큰 파일은 기존 `.env*` 제외 규칙으로 Git과 Vercel 업로드에서 제외된다. 토큰을 채팅, 로그, 커밋, public 디렉터리에 넣지 않는다.

## 사용과 검증

Codex의 `toonpick_discord_qa` MCP에는 두 읽기 전용 도구와 완료 표시 도구가 있다.

- `check_connection`: 봇 ID, Message Content Intent, 지정 서버·채널과 실제 메시지 조회를 검증한다.
- `read_qa`: 최신 QA의 본문, 작성·수정 시각, 원문 링크, 첨부 URL, 답장·스레드 ID와 봇의 ✅ 완료 표시 상태를 반환한다. `limit`은 1~100이다. `next_before`가 있으면 `before`로 전달해 이전 페이지를 읽는다. `thread_id`로 QA 스레드를 조회한다.
- `mark_qa_complete`: 지정된 #qa 원문의 모든 항목을 수정·검증한 뒤 ✅ 반응만 추가한다. 기존 체크 표시는 중복 추가하지 않는다. 텍스트 전송·삭제 기능은 제공하지 않는다. 봇에 메시지 기록 보기·반응 추가 권한이 필요하다.

MCP를 아직 불러오지 않은 채팅에서는 `.venv/discord-qa/Scripts/python.exe scripts/discord_qa.py --check`로 연결을 확인하고 `--read`로 QA를 읽을 수 있다. Codex에서 새 MCP를 불러오려면 앱을 다시 시작한다. 봇은 Gateway에 접속하지 않으므로 Discord의 온라인 표시는 연결 여부 판단 기준이 아니다.

자동 조회는 프로젝트의 `AGENTS.md`와 `Agent.md` 지침에 따라 작업을 시작할 때 수행한다. 사용자 요청으로 2026년 10월 31일 23:00(한국 시간)까지 1분 간격으로 새 QA를 확인하고 수정·검증·배포·✅ 표시까지 수행하는 이 채팅의 예약도 등록했다. 변경이 없으면 조용히 유지하며 23시 이후에는 새 QA 작업을 시작하지 않는다.

QA 작업을 마무리한 뒤 PC·태블릿·모바일의 세 분야 전체에서 레이아웃·검색·필터·보관함·상세 창·로딩·오류 상태·이미지·링크를 통합 점검한다. 23시에는 새 QA 조회를 종료하고, 진행 중 작업 및 최종 점검과 필요한 수정·검증을 마친 뒤 예약을 삭제하고 결과를 보고한다.

테스트: `.venv/discord-qa/Scripts/python.exe -m unittest discover -s tests -p test_discord_qa.py -v`. 테스트는 Discord에 접속하지 않으며, 채널 격리, 입력 검증, 페이지 조회, 첨부 정보, 토큰 로딩·오류 노출 방지, 요청 제한 처리, 연결 오판 방지와 MCP 표준입출력 통신을 확인한다.

## 근거

- [Discord 메시지 조회 API](https://docs.discord.com/developers/resources/message#get-channel-messages)
- [Discord 권한](https://docs.discord.com/developers/topics/permissions)
- [OpenAI 공식 MCP 설정 문서](https://learn.chatgpt.com/docs/extend/mcp)
- [공식 Python MCP SDK](https://py.sdk.modelcontextprotocol.io/)
