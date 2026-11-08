# My LivLiv v0.1.0

Windows용 로컬 캐릭터 마스크 편집기와 LivLiv Model Format v4 내보내기 도구입니다. My LivLiv는 LivLiv.ai의 공식 제품이 아닌 독립 개발 프로젝트입니다.

현재 버전은 이미지의 단순 테두리 배경을 제거하고, 사용자가 브러시로 파츠 마스크를 만들고 다듬어 `.livliv`로 저장하는 MVP입니다. 공식 LivLiv Player를 앱 안에서 사용해 실제 v4 패키지를 WebGL로 미리볼 수 있습니다. 의미 기반 AI 부위 인식과 가려진 영역 생성은 아직 포함하지 않습니다.

## 현재 동작하는 기능

- PNG, JPG, JPEG 이미지 불러오기. 이미지와 마스크는 로컬에서만 처리합니다.
- 테두리의 거의 단색인 배경을 flood-fill 방식으로 제거하고 가장자리에 1px 완충선을 적용합니다.
- 칠하기/지우개 브러시로 여러 투명 파츠 마스크를 수동 편집하고, 파츠 이름·표시 여부·순서·LivLiv 움직임 그룹을 수정합니다.
- 캔버스에서 머리 앵커 영역을 직접 지정합니다. 얼굴 특징을 자동 인식하지 않습니다.
- 프로젝트를 `.mlliv` ZIP으로 저장하고 다시 열 수 있습니다. 프로젝트에는 원본 이미지와 파츠 마스크가 포함됩니다.
- `model.json` v4와 크롭된 투명 PNG 텍스처를 `.livliv` ZIP으로 내보내고 경로, 캔버스 크기, JSON 필드, 텍스처 크기, 파일 누락을 확인합니다.
- 공식 LivLiv v4 JSON Schema로 항상 모델을 검사하고, 내보내기 또는 미리보기 생성 후 공식 Player 렌더러로 불러옵니다.
- Player 미리보기는 로컬 루프백 서버를 통해 메모리의 패키지를 제공합니다. 이미지와 모델은 외부 서버로 전송하지 않습니다.
- 공식 Player v0.3.0의 브라우저 배포 파일과 라이선스 고지를 포함해 인터넷 연결 없이 미리보기를 사용할 수 있습니다.
- 두 개의 자체 생성 CC0 테스트 캐릭터와 `.livliv`/`.mlliv` 예제를 제공합니다.

내보내는 v4 모델에는 공식 스키마에 정의된 `head`, `body`, `hair_back`, `hair_side`, `hair_front`, `hair_inner` 그룹만 기록합니다. 파츠 역할을 의미 없이 추측하지 않습니다. 눈·입 텍스처 프레임, 물리 체인, 표정 데이터는 자동 생성하지 않습니다.

## 요구 사항

- Windows 11
- Python 3.11 이상, 권장 3.12 또는 3.13
- PySide6 6.x (Qt WebEngine 포함)
- `jsonschema` 4.x: 내보내기와 미리보기 모두 공식 v4 JSON Schema 검증을 요구합니다.

## 실행

PowerShell에서 저장소 폴더로 이동한 뒤:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

이미지 편집 순서:

1. `이미지 열기`로 정면 캐릭터 그림을 엽니다.
2. 평탄한 배경이면 `테두리 배경 제거`를 적용하고 경계를 확인합니다.
3. `파츠 추가` 후 브러시로 머리/몸/머리카락 영역을 칠합니다. 각 파츠가 겹치면 원본 파츠의 지우개로 겹친 픽셀을 정리합니다.
4. 파츠별 움직임 그룹과 순서를 설정하고, `머리 앵커 그리기` 도구로 머리 영역을 드래그합니다.
5. `.mlliv` 프로젝트를 저장한 후 `.livliv`로 내보냅니다.

## 테스트

```powershell
python -m unittest discover -s tests -v
python scripts/generate_examples.py
```

두 테스트 아트워크는 이 프로젝트가 QPainter 도형으로 직접 만든 이미지입니다. 예제 디렉터리의 `LICENSE.md`에 따라 CC0 1.0으로 제공하며, 공식 Player 저장소의 캐릭터 에셋은 복사하지 않았습니다.

실제 환경에서 실행한 결과와 남은 제한은 [TEST_REPORT.md](TEST_REPORT.md)에 기록합니다. Windows 빌드 스크립트는 소스, 스키마, 공식 Player 런타임을 함께 묶습니다.

## 문서

- [ARCHITECTURE.md](ARCHITECTURE.md) — LivLiv Player와 v4 포맷 분석, 앱 구조
- [AI_MODELS.md](AI_MODELS.md) — AI 후보, 라이선스, 평가 한계
- [DEVELOPMENT.md](DEVELOPMENT.md) — 개발·빌드·프로젝트 보안
- [TEST_REPORT.md](TEST_REPORT.md) — 실제 검사 결과
- [ROADMAP.md](ROADMAP.md) — 남은 Phase 1 및 후속 계획

## 라이선스 및 출처

My LivLiv 코드는 Apache License 2.0으로 제공합니다. 동봉한 `schemas/livliv-model-v4.json`은 공개된 LivLiv Player 저장소의 스키마를 원문 그대로 포함합니다. 공식 Player v0.3.0 브라우저 런타임은 `runtime/vendor/player-0.3.0/`에 포함하며, 해당 패키지의 Apache 2.0 라이선스와 NOTICE를 함께 보존했습니다. Player의 샘플 캐릭터와 선택형 AI/VRM 의존성은 포함하지 않습니다. 출처와 라이선스는 [NOTICE](NOTICE)를 확인하세요.

LivLiv Model Format v4 설명은 [공식 FORMAT.md](https://github.com/livliv-dev/player/blob/main/FORMAT.md), Player API는 [공식 API.md](https://github.com/livliv-dev/player/blob/main/API.md), 엔진은 [LivLiv Player 저장소](https://github.com/livliv-dev/player)를 기준으로 했습니다. LivLiv는 Live2D Cubism `.moc3`/`.cmo3`와 호환되지 않습니다.
