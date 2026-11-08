# AI 모델 검토

## v0.1.0 선택

v0.1.0에서는 AI 모델을 설치·사용하지 않습니다. 구현된 자동 처리는 `QImage` 기반 경계 색 flood-fill이며, 한 가지 색에 가까운 배경만 빠르게 제거합니다. 두 개의 CC0 벡터 예제와 사용자가 요청한 다운로드 이미지로 절차를 확인했지만, 이 결과는 AI 인식 정확도나 애니메이션풍 전체 데이터셋의 정확도 측정이 아닙니다.

## 후보 비교

| 후보 | 맞는 작업 | 크기·가속·오프라인 | 라이선스·제한 | 판단 |
|---|---|---|---|---|
| SkyTNT Anime Segmentation / ISNet | 애니메이션 인물 전경/배경 마스크. 얼굴·눈·옷을 각 파츠로 나누지는 않음 | 공식 Hugging Face 모델 페이지에 `isnetis.onnx` 176 MB가 표시됩니다. 다운로드 후 로컬 추론 가능. ONNX 내보내기 코드가 있음. CPU 속도와 메모리는 이 프로젝트에서 미측정 | 저장소 코드와 모델 허브 페이지는 Apache-2.0로 표시됨. 실제 가중치 파일/버전과 라이선스·체크섬을 내려받기 전에 다시 확인해야 함 | 다음 배경 제거 품질 후보. 실제 애니메이션 이미지에서 비교한 뒤 도입 |
| Meta SAM 2.1 | 점/상자 프롬프트로 임의 객체 마스크를 제안. 머리, 얼굴, 앞머리 등 명칭을 자동 분류하지 않음 | tiny/small/base+/large 체크포인트가 있음. 모델 변형에 따라 다운로드·메모리 비용이 달라지고, 이 PC의 ONNX 변환·CPU/GPU 시간은 미측정. 프롬프트 기반 수동 보정에 적합 | 모델 코드와 체크포인트는 Apache-2.0 | 사용자가 클릭/상자를 지정하는 편집 보조 후보. 자동 파츠 인식용으로 단독 선정하지 않음 |
| Meta SAM 3 | 텍스트/시각 개념 프롬프트로 이미지 안 개념을 분할할 수 있음 | 모델 가중치가 공개되어도 크기·Windows/Intel Arc 추론은 본 프로젝트에서 미측정 | 별도 SAM License이며 SAM 2의 Apache-2.0와 다릅니다. 배포 전에 사용/재배포 조건을 별도로 검토해야 함 | v0.1.0에는 사용하지 않음 |
| MediaPipe Face Landmarker | 실제 사람 얼굴 랜드마크와 blendshape 추정 | 공식 설명은 478개 3D 랜드마크, 여러 모델 단계, 192×192/256×256 입력을 제시합니다. 모델 파일은 별도 내려받아야 함. CPU/Arc 처리 시간은 미측정 | 사람 얼굴 추정용입니다. 정면 애니메이션 일러스트에서 정확하다고 가정하지 않음. 모델 번들 내 구성요소의 재배포 라이선스 확인 전 배포하지 않음 | 실시간 웹캠 추적 후보이지, 정지 일러스트 파츠 자동 생성 후보는 아님 |
| OpenCV GrabCut / 색 flood-fill | 전경 마스크를 사용자가 지정한 영역/전경·배경 힌트로 개선 | 작은 CPU 경로, 모델 파일 없음. 이 버전은 직접 구현한 테두리 연결 flood-fill만 사용 | OpenCV 없이 QImage로 구현해 추가 라이선스와 다운로드가 없음. 단색 배경에서만 안정적 | 현재 선택. 품질 한계를 화면에 표시 |

## 검토 근거 및 측정 한계

- Anime Segmentation은 애니메이션 캐릭터 마스크 학습 데이터와 ISNet, U2Net, MODNet, InSPyReNet 모델을 설명하며 ONNX 내보내기 절차를 제공합니다. [공식 저장소](https://github.com/SkyTNT/anime-segmentation), [모델 허브](https://huggingface.co/skytnt/anime-seg)
- SAM 2 문서는 이미지/비디오의 promptable segmentation, tiny부터 large까지의 체크포인트, Apache-2.0 사용 조건을 설명합니다. [공식 저장소](https://github.com/facebookresearch/sam2)
- SAM 3은 별도 이용 조건을 둔 모델입니다. [공식 저장소와 라이선스](https://github.com/facebookresearch/sam3)
- MediaPipe Face Landmarker는 얼굴 검출, 478개 랜드마크, blendshape 예측을 결합한 인간 얼굴 태스크입니다. [공식 문서](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker)
- 현재 ONNX Runtime 문서는 내장 OpenVINO EP를 deprecated로 표시하고 standalone plugin을 권장합니다. Intel CPU/GPU/NPU 장치는 각 런타임과 그래픽/NPU 드라이버가 필요합니다. [OpenVINO Plugin EP 빠른 시작](https://github.com/onnxruntime/onnxruntime-ep-openvino/blob/main/docs/QuickStart.md)

실제 시험은 평탄한 배경의 CC0 도형 이미지 2종과 사용자가 지정한 로컬 일러스트 1종의 테두리 배경 제거·PNG 마스크 생성으로 제한합니다. AI 후보 모델 가중치를 내려받거나 실행하지 않았으므로 모델 정확도·FPS·RAM·Intel Arc 성능을 추정값으로 보고하지 않습니다.
