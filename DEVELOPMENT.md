# 개발 및 패키지 안전

## 실행 환경

Python 3.11+와 PySide6를 사용합니다. Qt 이미지 플러그인이 PNG/JPG를 디코드하고 모든 내부 픽셀 편집은 QImage로 수행됩니다. AI 런타임은 현재 포함되지 않습니다.

```powershell
python -m pip install -r requirements.txt
python main.py
```

Windows 앱 폴더를 만들려면 PyInstaller가 필요합니다.

```powershell
.\scripts\build_windows.ps1
```

이 스크립트는 현재 Python 환경에서 `dist\My LivLiv`를 생성하도록 설정돼 있습니다. Python/PyInstaller 조합에 따라 추가 조정이 필요할 수 있으며, v0.1.0에서는 설치 파일을 만들거나 서명하지 않았습니다.

## 데이터 형식

- `.mlliv`: My LivLiv 프로젝트 ZIP. `project.json`, `source.png`, `masks/layer_NNN.png`를 포함합니다.
- `.livliv`: 공식 형식 ZIP. 루트 `model.json` 다음에 `textures/*.png` 파츠 이미지를 저장합니다. 이미지와 JSON은 STORE 방식입니다.

프로젝트 로더는 ZIP 엔트리 수/압축 해제 크기/파일 크기를 제한하고, 중복 경로, 절대 경로, `..`, 역슬래시, 심볼릭 링크, 암호화 엔트리를 거부합니다. 파일을 디스크에 무조건 압축 해제하지 않고 검사된 이름만 메모리에서 읽습니다.

모델 내보내기는 official v4 JSON Schema 사본을 포함합니다. `jsonschema`가 설치되면 Draft 2020-12 검증기를 실행합니다. 없으면 모델 헤더, 필수 앵커, ID, 그룹, 이미지 경로, 좌표, 파일 존재 및 텍스처 크기를 자체 검사합니다. 두 경로의 차이는 내보내기 완료 대화상자 대신 `TEST_REPORT.md`에 구분해 기록합니다.

원본 이미지와 마스크는 선택한 `.mlliv` 프로젝트에 포함됩니다. `.livliv`에는 내보내기 시 표시된 레이어의 투명 텍스처가 들어갑니다. 외부 서버 업로드 코드나 원격 AI 요청은 없습니다.
