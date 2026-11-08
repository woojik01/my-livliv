# 구조와 LivLiv Player 분석

분석 기준은 2026-11-08에 확인한 `livliv-dev/player` 기본 브랜치 트리 `0f2c8871de375dfe4d239fab480e07f6d9b032dd`입니다. 공식 문서는 Model Format v4(2026년 11월)와 `schema/livliv-model-v4.json`을 제공합니다.

## 공식 Player에서 확인한 구조

- `src/index.ts`가 Player API 진입점이고, 실제 그리기·리깅·포맷 처리는 `src/runtime/`에 있습니다. 공개 패키지는 `@livliv-dev/player`입니다.
- Player는 WebGL2로 레이어를 캔버스 좌표에서 그립니다. `.livliv`는 ZIP이고 `model.json`이 루트에, 파츠 이미지는 `textures/`에 있습니다. 현재 포맷의 필수 이미지는 PNG 또는 WebP가 될 수 있습니다.
- `layers` 순서는 아래에서 위로 그리는 순서입니다. 각 파츠는 `texture`, 캔버스 위치 `x/y`, 이미지 크기 `w/h`, 움직임 그룹을 가집니다. 레이어 텍스처는 straight alpha여야 합니다.
- 공식 그룹은 `head`, `body`, `hair_back`, `hair_side`, `hair_front`, `hair_inner`입니다. 알 수 없는 `role`은 일반 레이어로 그리지만, 알 수 없는 그룹은 거부할 수 있습니다.
- Player 파라미터에는 `angleX/Y/Z`, 좌·우 눈 개폐, 시선, 눈썹, 입 열림/모음, 미소, 몸 회전, 호흡이 있습니다. 눈 역할(`eye_L/R`, `lid_L/R`, `iris_L/R`)과 입 프레임/viseme를 따로 준비해야 해당 동작을 제대로 표현합니다.
- 머리 회전·기울기·부피, 가슴 호흡, 목, 전면/측면/후면 머리카락 spring-chain 설정은 v4 `rig`에 들어갑니다. 자체 스프링 체인은 `rig.chains`와 레이어의 `bones`가 서로 맞아야 합니다.
- v4 JSON Schema는 최상위 임의 필드를 금지하고, 필수 파일·레이어 참조·패키지 경로 안전 규칙도 요구합니다. 예제 캐릭터는 코드 라이선스와 다른 별도 이용 약관을 가지므로 이 제작기의 테스트 아트에 사용하지 않았습니다.

## 현재 구현

```text
main.py                     PySide6 진입점
mlliv/core.py               QImage 가져오기, 테두리 색 flood-fill, 마스크, 알파 합성
mlliv/app.py                한국어 데스크톱 UI, 레이어/브러시/앵커 편집
mlliv/package_io.py         안전 제한을 둔 .mlliv 입출력과 LivLiv v4 내보내기/검사
schemas/livliv-model-v4.json 공식 v4 스키마 사본
examples/                   자체 생성한 테스트 이미지와 모델
tests/                      이미지 처리·프로젝트 ZIP·모델 패키지 검사
```

`QImage`의 CPU 이미지 처리를 사용하며, 외부 API로 이미지를 보내지 않습니다. 배경 제거는 테두리에서 이어지는 색 영역을 찾는 고전적 flood-fill입니다. 인물 인식·머리카락 세분화 모델이 아닙니다. 사용자가 마스크 브러시로 파츠를 만들고 수동 앵커를 지정합니다.

현재 미리보기는 파츠 그룹에 2D 회전을 시험하는 앱 내부 프리뷰입니다. **공식 Player 엔진을 embed하지 않았고**, 공식 Player의 WebGL 렌더 결과를 대체한다고 주장하지 않습니다. Player 소스와 의존성은 이 환경에서 npm으로 받을 수 없었고 PySide6 WebEngine도 설치되어 있지 않았습니다. 따라서 생성 파일을 공식 Player에 직접 로드하는 통합 검증은 남아 있습니다.

## 아직 생성하지 않는 정보

자동 얼굴 랜드마크, 눈/입 역할, 눈 깜빡임용 대체 레이어, 입 viseme, 표정, 가려진 영역 복원, spring-chain 데이터는 생성하지 않습니다. 이 데이터 없이 해당 동작이 자동으로 작동한다고 표시하지 않습니다. 일반 레이어와 수동 앵커는 v4 구조로 내보내며, 공식 Player의 장기 테스트를 아직 하지 않았습니다.
