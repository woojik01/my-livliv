# 개발 및 패키지 안전

## 실행 환경

Python 3.11+와 PySide6(Qt WebEngine 포함)를 사용합니다. Qt 이미지 플러그인이 PNG/JPG를 디코드하고 모든 내부 픽셀 편집은 QImage로 수행됩니다. `jsonschema`로 공식 v4 스키마를 항상 검증합니다. AI 런타임은 현재 포함되지 않습니다.

```powershell
python -m pip install -r requirements.txt
python main.py
```

Windows 앱 폴더를 만들려면 PyInstaller가 필요합니다.

```powershell
.\scripts\build_windows.ps1
```

이 스크립트는 프로젝트 가상 환경(있으면)을 사용해 `dist\My LivLiv`를 생성합니다. PyInstaller에는 스키마와 `runtime/`을 함께 전달합니다. Python/PyInstaller 조합에 따라 추가 조정이 필요할 수 있으며, 앱은 아직 설치 프로그램으로 서명되지 않았습니다.

## 데이터 형식

- `.mlliv`: My LivLiv 프로젝트 ZIP. `project.json`, `source.png`, `masks/layer_NNN.png`를 포함합니다.
- `.livliv`: 공식 형식 ZIP. 루트 `model.json` 다음에 `textures/*.png` 파츠 이미지를 저장합니다. 이미지와 JSON은 STORE 방식입니다.

프로젝트 로더는 ZIP 엔트리 수/압축 해제 크기/파일 크기를 제한하고, 중복 경로, 절대 경로, `..`, 역슬래시, 심볼릭 링크, 암호화 엔트리를 거부합니다. 파일을 디스크에 무조건 압축 해제하지 않고 검사된 이름만 메모리에서 읽습니다.

모델 내보내기와 미리보기는 동봉한 공식 v4 JSON Schema 사본으로 Draft 2020-12 검증기를 실행합니다. `jsonschema`가 없거나 스키마 파일이 빠진 경우 조용히 간이 검사로 대체하지 않고 작업을 중단합니다.

원본 이미지와 마스크는 선택한 `.mlliv` 프로젝트에 포함됩니다. `.livliv`에는 내보내기 시 표시된 레이어의 투명 텍스처가 들어갑니다. Player 탭은 `127.0.0.1`의 임의 포트, 매 실행마다 바뀌는 비밀 경로에서 정적 런타임 파일과 메모리 패키지만 제공합니다. POST 요청을 받지 않고 엄격한 CSP를 설정하며, 패키지를 디스크에 임시 저장하지 않습니다. 외부 서버 업로드 코드나 원격 AI 요청은 없습니다.

## 공식 Player 미리보기 런타임

`runtime/vendor/player-0.3.0/`에는 공식 `@livliv-dev/player@0.3.0`의 브라우저 엔트리와 해당 엔트리가 불러오는 JavaScript 청크만 포함합니다. `runtime/package-lock.json`에 npm 아카이브의 무결성 값을 기록하고, 배포본 옆에 upstream `LICENSE` 및 `NOTICE`를 보존합니다. Node.js는 앱 실행에 필요하지 않습니다. Qt WebEngine이 로컬 페이지를 열고 LivLiv 패키지 Blob을 공식 Player API에 전달합니다.

앱에서 미리보기 생성 버튼을 누르면 현재 문서의 이미지와 마스크를 복사한 뒤 작업자 스레드에서 v4 패키지를 만들고 검증합니다. 편집 중인 QImage를 동시에 읽지 않으며, 생성한 바이트만 로컬 서버에 넘깁니다. 패키지를 디스크에 기록하려면 내보내기 기능을 사용합니다.
