import { Player } from "./vendor/player-0.3.0/dist/index.js";

const canvas = document.querySelector("#player");
const status = document.querySelector("#status");
const empty = document.querySelector("#empty");
let player = null;
let request = 0;

function showStatus(message) {
  status.textContent = message;
}

function createPlayer() {
  if (!Player.isSupported()) {
    showStatus("이 PC의 브라우저 환경에서 WebGL2를 사용할 수 없습니다.");
    return null;
  }
  try {
    return new Player(canvas, {
      idle: false,
      followPointer: false,
      maxPixelRatio: 1,
      autoplay: true,
      lang: "ko",
    });
  } catch (error) {
    showStatus(`Player 시작 실패: ${error.message}`);
    return null;
  }
}

player = createPlayer();

async function loadLatest() {
  if (!player) return false;
  const current = ++request;
  showStatus("모델 패키지를 여는 중입니다…");
  try {
    const response = await fetch(`./api/model.livliv?rev=${Date.now()}`, { cache: "no-store" });
    if (response.status === 404) {
      if (current === request) showStatus("편집 후 Player 미리보기 만들기를 누르세요.");
      return false;
    }
    if (!response.ok) throw new Error(`로컬 패키지 읽기 실패 (${response.status})`);
    const packageFile = await response.blob();
    if (current !== request) return false;
    const info = await player.load(packageFile);
    if (current !== request) return false;
    empty.hidden = true;
    showStatus(`${info.name} · ${info.size[0]} × ${info.size[1]} · ${info.format} v${info.version}`);
    return true;
  } catch (error) {
    if (current === request && error.name !== "AbortError") {
      showStatus(`모델을 불러오지 못했습니다: ${error.message}`);
      empty.hidden = false;
    }
    return false;
  }
}

function setParams(values) {
  if (!player) return;
  const ranges = {
    angleX: [-30, 30], angleY: [-30, 30], angleZ: [-30, 30],
    eyeLOpen: [0, 1], eyeROpen: [0, 1], mouthOpen: [0, 1], smile: [0, 1],
  };
  for (const [key, value] of Object.entries(values)) {
    const range = ranges[key];
    if (!range || !Number.isFinite(value)) continue;
    player.params[key] = Math.max(range[0], Math.min(range[1], value));
  }
}

function blink() {
  setParams({ eyeLOpen: 0, eyeROpen: 0 });
  window.setTimeout(() => setParams({ eyeLOpen: 1, eyeROpen: 1 }), 140);
}

function action(name) {
  if (["nod", "shake", "tilt", "hop", "shy"].includes(name)) player?.act(name);
}

function expression(name) {
  if (!player) return false;
  const applied = player.setExpression(name);
  if (!applied) showStatus(`이 모델에는 '${name}' 표정 파츠가 없습니다.`);
  return applied;
}

window.MyLivLivPreview = { loadLatest, setParams, blink, action, expression };
showStatus("공식 Player 준비 완료 · 모델을 만들면 여기에 표시합니다.");
