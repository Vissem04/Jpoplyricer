// ===== 인증/승인 게이트 =====
const topBar = document.getElementById("topBar");
const appMain = document.getElementById("appMain");
const authOverlay = document.getElementById("authOverlay");
const pendingOverlay = document.getElementById("pendingOverlay");
const adminBtn = document.getElementById("adminBtn");
const userLabel = document.getElementById("userLabel");
const logoutBtn = document.getElementById("logoutBtn");
const loginForm = document.getElementById("loginForm");
const registerForm = document.getElementById("registerForm");
const authMsg = document.getElementById("authMsg");
const adminOverlay = document.getElementById("adminOverlay");
const adminClose = document.getElementById("adminClose");
const adminList = document.getElementById("adminList");

let currentUser = null;

function applyAuthState(user) {
  currentUser = user;
  const approved = user && (user.role === "admin" || user.status === "approved");
  authOverlay.classList.toggle("hidden", !!user);
  pendingOverlay.classList.toggle("hidden", !(user && !approved));
  appMain.classList.toggle("hidden", !approved);
  topBar.classList.toggle("hidden", !approved);
  if (approved) {
    userLabel.textContent = user.username + (user.role === "admin" ? " (관리자)" : "");
    adminBtn.classList.toggle("hidden", user.role !== "admin");
  }
  if (user && !approved) {
    const rejected = user.status === "rejected";
    document.getElementById("pendingTitle").textContent = rejected
      ? "가입이 거절되었습니다"
      : "관리자 승인 대기 중";
    document.getElementById("pendingDesc").textContent = rejected
      ? "관리자에게 문의해 주세요."
      : "관리자가 승인하면 바로 이용할 수 있어요. 잠시 후 다시 시도해 주세요.";
  }
}

async function refreshAuth() {
  try {
    const res = await fetch("/api/auth/me");
    applyAuthState(await res.json());
  } catch {
    applyAuthState(null);
  }
}

// 탭 전환
document.querySelectorAll(".auth-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".auth-tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    const isLogin = tab.dataset.tab === "login";
    loginForm.classList.toggle("hidden", !isLogin);
    registerForm.classList.toggle("hidden", isLogin);
    authMsg.textContent = "";
  });
});

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  authMsg.textContent = "";
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("loginUser").value.trim(),
        password: document.getElementById("loginPass").value,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      authMsg.textContent = "❌ " + (data.detail || "로그인 실패");
      return;
    }
    applyAuthState(data);
  } catch (err) {
    authMsg.textContent = "❌ " + err.message;
  }
});

registerForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  authMsg.textContent = "";
  try {
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: document.getElementById("regUser").value.trim(),
        password: document.getElementById("regPass").value,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      authMsg.textContent = "❌ " + (data.detail || "가입 실패");
      return;
    }
    document.querySelector('.auth-tab[data-tab="login"]').click();
    authMsg.classList.add("ok");
    authMsg.textContent = "✓ 가입 신청 완료! 관리자 승인 후 로그인하세요.";
  } catch (err) {
    authMsg.textContent = "❌ " + err.message;
  }
});

async function doLogout() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch {}
  applyAuthState(null);
}
logoutBtn.addEventListener("click", doLogout);
document.getElementById("pendingLogout").addEventListener("click", doLogout);
document.getElementById("pendingRefresh").addEventListener("click", refreshAuth);

// ===== 관리자 패널 =====
function openAdmin() {
  adminOverlay.classList.remove("hidden");
  loadAdminUsers();
}
function closeAdmin() {
  adminOverlay.classList.add("hidden");
}

async function loadAdminUsers() {
  adminList.innerHTML = '<div class="library-empty">불러오는 중…</div>';
  try {
    const res = await fetch("/api/admin/users");
    const users = await res.json();
    if (!res.ok) {
      adminList.innerHTML = `<div class="library-empty">${escapeHtml(users.detail || "오류")}</div>`;
      return;
    }
    adminList.innerHTML = users
      .map((u) => {
        const badge =
          u.status === "approved"
            ? '<span class="ustat ok">승인됨</span>'
            : u.status === "rejected"
            ? '<span class="ustat no">거절됨</span>'
            : '<span class="ustat wait">대기중</span>';
        const actions =
          u.role === "admin"
            ? `<span class="ustat admin">관리자</span>
               <button class="uact demote" data-demote="${escapeHtml(u.username)}">관리자 해제</button>`
            : `
              <button class="uact promote" data-promote="${escapeHtml(u.username)}">관리자 지정</button>
              <button class="uact approve" data-approve="${escapeHtml(u.username)}">승인</button>
              <button class="uact reject" data-reject="${escapeHtml(u.username)}">거절</button>
              <button class="uact del" data-deluser="${escapeHtml(u.username)}">🗑</button>`;
        return `
          <div class="user-row">
            <div class="user-info">
              <div class="user-name">${escapeHtml(u.username)} ${badge}</div>
              <div class="library-item-date">${escapeHtml((u.created || "").replace("T", " "))}</div>
            </div>
            <div class="user-actions">${actions}</div>
          </div>`;
      })
      .join("");
  } catch (err) {
    adminList.innerHTML = `<div class="library-empty">${escapeHtml(err.message)}</div>`;
  }
}

adminList.addEventListener("click", async (e) => {
  const ap = e.target.closest("[data-approve]");
  const rj = e.target.closest("[data-reject]");
  const dl = e.target.closest("[data-deluser]");
  const pr = e.target.closest("[data-promote]");
  const dm = e.target.closest("[data-demote]");
  if (ap) await fetch(`/api/admin/users/${encodeURIComponent(ap.dataset.approve)}/approve`, { method: "POST" });
  else if (rj) await fetch(`/api/admin/users/${encodeURIComponent(rj.dataset.reject)}/reject`, { method: "POST" });
  else if (pr) {
    if (!confirm(`'${pr.dataset.promote}' 사용자에게 관리자 권한을 부여할까요?`)) return;
    const r = await fetch(`/api/admin/users/${encodeURIComponent(pr.dataset.promote)}/role?value=admin`, { method: "POST" });
    if (!r.ok) alert("실패: " + ((await r.json()).detail || ""));
  } else if (dm) {
    if (!confirm(`'${dm.dataset.demote}' 의 관리자 권한을 해제할까요?`)) return;
    const r = await fetch(`/api/admin/users/${encodeURIComponent(dm.dataset.demote)}/role?value=user`, { method: "POST" });
    if (!r.ok) alert("실패: " + ((await r.json()).detail || ""));
    else refreshAuth(); // 내가 나를 해제한 경우 상태 갱신
  } else if (dl) {
    if (!confirm(`'${dl.dataset.deluser}' 사용자를 삭제할까요?`)) return;
    await fetch(`/api/admin/users/${encodeURIComponent(dl.dataset.deluser)}`, { method: "DELETE" });
  } else return;
  loadAdminUsers();
});

adminBtn.addEventListener("click", openAdmin);
adminClose.addEventListener("click", closeAdmin);
adminOverlay.addEventListener("click", (e) => {
  if (e.target === adminOverlay) closeAdmin();
});

refreshAuth(); // 시작 시 인증 상태 확인

// ===== 이하 기존 앱 =====
const form = document.getElementById("form");
const urlInput = document.getElementById("url");
const submitBtn = document.getElementById("submit");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const metaEl = document.getElementById("meta");
const lyricsEl = document.getElementById("lyrics");
const playerEl = document.getElementById("player");
const audioEl = document.getElementById("audio");
const playBtn = document.getElementById("playBtn");
const curTimeEl = document.getElementById("curTime");
const durTimeEl = document.getElementById("durTime");
const seekBar = document.getElementById("seekBar");
const muteBtn = document.getElementById("muteBtn");
const volBar = document.getElementById("volBar");
const karaokeToggle = document.getElementById("karaokeMode");
const offsetRange = document.getElementById("offsetRange");
const offsetValue = document.getElementById("offsetValue");
const offsetMinus = document.getElementById("offsetMinus");
const offsetPlus = document.getElementById("offsetPlus");
const offsetReset = document.getElementById("offsetReset");
const offsetAuto = document.getElementById("offsetAuto");
const offsetHint = document.getElementById("offsetHint");

let suggestedOffset = null; // 서버가 추정한 자동 오프셋

const lyricsToolbar = document.getElementById("lyricsToolbar");
const copyModeToggle = document.getElementById("copyModeToggle");
const copyBtn = document.getElementById("copyBtn");
const copyFeedback = document.getElementById("copyFeedback");
const lyricsOnlyBtn = document.getElementById("lyricsOnlyBtn");
const editBtn = document.getElementById("editBtn");
const editToolbar = document.getElementById("editToolbar");
const editSaveBtn = document.getElementById("editSaveBtn");
const editCancelBtn = document.getElementById("editCancelBtn");
const libraryBtn = document.getElementById("libraryBtn");
const libraryOverlay = document.getElementById("libraryOverlay");
const libraryClose = document.getElementById("libraryClose");
const libraryClearAll = document.getElementById("libraryClearAll");
const libraryList = document.getElementById("libraryList");

let lineEls = []; // .line DOM 요소 배열
let lineStarts = []; // 각 줄 시작시각(초)
let currentLines = []; // 현재 가사 데이터 {original, reading, translation}
let currentSongId = null; // 현재 곡 id(라이브러리 저장 키)
let currentTitle = ""; // 현재 곡 제목(새 창 가사 보기용)
let currentArtist = ""; // 현재 곡 아티스트
let editMode = false;
let activeIdx = -1;

// 싱크 오프셋(초): effective_start = lineStarts[i] + offset. localStorage에 저장.
let syncOffset = parseFloat(localStorage.getItem("syncOffset") || "0") || 0;

function effectiveStart(i) {
  return lineStarts[i] == null ? null : lineStarts[i] + syncOffset;
}

function setOffset(v) {
  syncOffset = Math.max(-5, Math.min(5, Math.round(v * 10) / 10));
  localStorage.setItem("syncOffset", String(syncOffset));
  offsetRange.value = String(syncOffset);
  offsetValue.textContent = (syncOffset >= 0 ? "+" : "") + syncOffset.toFixed(1) + "s";
  activeIdx = -1; // 다음 timeupdate에서 즉시 재계산
}

offsetRange.addEventListener("input", () => setOffset(parseFloat(offsetRange.value)));
offsetMinus.addEventListener("click", () => setOffset(syncOffset - 0.1));
offsetPlus.addEventListener("click", () => setOffset(syncOffset + 0.1));
offsetReset.addEventListener("click", () => setOffset(0));
offsetAuto.addEventListener("click", () => {
  if (suggestedOffset != null) setOffset(suggestedOffset);
});
setOffset(syncOffset); // 초기 표시

// ===== 맨 위로 버튼 =====
const scrollTopBtn = document.getElementById("scrollTopBtn");
window.addEventListener("scroll", () => {
  scrollTopBtn.classList.toggle("hidden", window.scrollY < 300);
});
scrollTopBtn.addEventListener("click", () =>
  window.scrollTo({ top: 0, behavior: "smooth" })
);

function showStatus(html, isError = false) {
  statusEl.classList.remove("hidden");
  statusEl.classList.toggle("error", isError);
  statusEl.innerHTML = html;
}

function hideStatus() {
  statusEl.classList.add("hidden");
}

// ===== 진행 게이지바 =====
let progressTimer = null;

function showProgress() {
  statusEl.classList.remove("hidden", "error");
  statusEl.innerHTML = `
    <div class="progress-wrap">
      <div class="progress-track"><div id="progressBar" class="progress-bar"></div></div>
      <div id="progressLabel" class="progress-label">준비 중… 0%</div>
    </div>`;
  startProgress();
}

function startProgress() {
  const stages = [
    { t: 0, text: "오디오 다운로드 중…" },
    { t: 8000, text: "음성 인식 중…" },
    { t: 22000, text: "곡 추론 · 가사 검색 중…" },
    { t: 34000, text: "독음 · 해석 생성 중…" },
    { t: 48000, text: "노래방 싱크 맞추는 중…" },
  ];
  const start = performance.now();
  let pct = 0;
  stopProgress();
  progressTimer = setInterval(() => {
    const bar = document.getElementById("progressBar");
    const label = document.getElementById("progressLabel");
    if (!bar || !label) return;
    const elapsed = performance.now() - start;
    pct += (95 - pct) * 0.045; // 95%로 점근(완료 응답 전까지 가득 차지 않음)
    bar.style.width = pct.toFixed(1) + "%";
    let cur = stages[0].text;
    for (const s of stages) if (elapsed >= s.t) cur = s.text;
    label.textContent = `${cur} ${Math.round(pct)}%`;
  }, 180);
}

function stopProgress() {
  if (progressTimer) {
    clearInterval(progressTimer);
    progressTimer = null;
  }
}

function finishProgress() {
  stopProgress();
  const bar = document.getElementById("progressBar");
  const label = document.getElementById("progressLabel");
  if (bar) bar.style.width = "100%";
  if (label) label.textContent = "완료 100%";
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return;

  submitBtn.disabled = true;
  resultEl.classList.add("hidden");
  metaEl.innerHTML = "";
  lyricsEl.innerHTML = "";
  showProgress();

  try {
    const res = await fetch("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    const data = await res.json();

    if (res.status === 401) {
      stopProgress();
      refreshAuth();
      return;
    }
    if (!res.ok) {
      stopProgress();
      showStatus("❌ " + (data.detail || "알 수 없는 오류"), true);
      return;
    }

    finishProgress();
    renderResult(data);
    setTimeout(hideStatus, 500);
  } catch (err) {
    stopProgress();
    showStatus("❌ 네트워크 오류: " + err.message, true);
  } finally {
    submitBtn.disabled = false;
  }
});

function renderResult(data) {
  const g = data.source || data.genius || {}; // source(신규) 우선, 구버전 저장본은 genius
  const srcName = g.name || "Genius";
  const conf = Math.round((data.identified?.confidence || 0) * 100);
  const sync =
    data.sync_method === "synced"
      ? '<span class="badge precise" title="동기가사 구조 + 이 음원 음성정렬(가장 정확)">정밀 싱크</span>'
      : data.sync_method === "word"
      ? '<span class="badge precise" title="이 음원의 음성 단어 타임스탬프에 가사를 정렬">정밀 싱크 (음성정렬)</span>'
      : data.sync_method === "lrc"
      ? '<span class="badge precise" title="동기가사(LRCLIB) 기반 정밀 싱크">정밀 싱크 (동기가사)</span>'
      : data.sync_method === "forced"
      ? '<span class="badge precise">정밀 싱크</span>'
      : data.sync_method === "even"
      ? '<span class="badge approx">싱크 없음(반주)</span>'
      : '<span class="badge approx">근사 싱크</span>';
  const tj =
    data.tj_number
      ? `<span class="badge tj">TJ 노래방 ${escapeHtml(String(data.tj_number))}</span>`
      : `<span class="badge tj-none">TJ 노래방 -</span>`;
  // 교차검증 배지: 두 출처 일치/불일치
  let xc = "";
  const cc = data.cross_check;
  if (cc && cc.agreement != null) {
    xc = cc.conflict
      ? '<span class="badge approx" title="출처마다 가사가 달라요. 가사 수정으로 보정하세요.">⚠️ 출처 간 가사 차이</span>'
      : '<span class="badge precise" title="두 가사 사이트의 내용이 일치">✓ 출처 2곳 일치</span>';
  }
  metaEl.innerHTML = `
    <h2>${escapeHtml(g.title || "")}</h2>
    <div class="artist">${escapeHtml(g.artist || "")}</div>
    <div style="margin-top:6px">
      <a href="${g.url}" target="_blank" rel="noopener">${escapeHtml(srcName)}에서 보기 ↗</a>
      <span style="color:var(--muted);font-size:0.8rem"> · 곡 추론 신뢰도 ${conf}%</span>
      ${sync}
      ${xc}
      ${tj}
    </div>
  `;

  // 오디오 플레이어
  if (data.audio_url) {
    audioEl.src = data.audio_url;
    playerEl.classList.remove("hidden");
  } else {
    audioEl.removeAttribute("src");
    playerEl.classList.add("hidden");
  }
  currentTitle = g.title || "";
  currentArtist = g.artist || "";

  // 자동 오프셋 적용
  suggestedOffset = typeof data.suggested_offset === "number" ? data.suggested_offset : null;
  if (suggestedOffset != null) {
    setOffset(suggestedOffset);
    offsetAuto.disabled = false;
    if (Math.abs(suggestedOffset) < 0.05) {
      offsetHint.textContent =
        "싱크가 정확히 맞아 자동 보정이 필요 없어요. 어긋나면 슬라이더로 조정하세요.";
    } else {
      offsetHint.textContent =
        `자동 보정 ${suggestedOffset >= 0 ? "+" : ""}${suggestedOffset.toFixed(1)}s 적용됨 · 슬라이더로 더 미세조정하세요.`;
    }
  } else {
    offsetAuto.disabled = true;
    offsetHint.textContent = "가사가 음악보다 빠르면 +쪽, 느리면 −쪽으로 조정하세요.";
  }

  // 가사 줄 렌더
  currentLines = data.lines;
  currentSongId = data.id || null;
  editMode = false;
  lyricsToolbar.classList.toggle("hidden", data.lines.length === 0);
  copyFeedback.textContent = "";
  lineStarts = makeIncreasing(data.lines.map((ln) => ln.start));
  renderLyricsNormal();

  resultEl.classList.remove("hidden");
}

function renderLyricsNormal() {
  editMode = false;
  editToolbar.classList.add("hidden");
  lyricsEl.innerHTML = currentLines
    .map(
      (ln, i) => `
      <div class="line" data-idx="${i}">
        <div class="original">${escapeHtml(ln.original)}</div>
        <div class="reading">${escapeHtml(ln.reading)}</div>
        <div class="translation">${escapeHtml(ln.translation)}</div>
      </div>`
    )
    .join("");

  lineEls = Array.from(lyricsEl.querySelectorAll(".line"));
  activeIdx = -1;

  // 가사 줄 클릭 -> 해당 타이밍으로 이동 (오프셋 반영)
  lineEls.forEach((el, i) => {
    el.addEventListener("click", () => {
      const s = effectiveStart(i);
      if (s != null && !isNaN(audioEl.duration)) {
        audioEl.currentTime = Math.max(0, s);
        audioEl.play();
      }
    });
  });
}

function renderLyricsEdit() {
  editMode = true;
  editToolbar.classList.remove("hidden");
  lineEls = [];
  activeIdx = -1;
  lyricsEl.innerHTML = currentLines
    .map(
      (_, i) => `
      <div class="line-edit">
        <input class="edit-field edit-original" data-idx="${i}" placeholder="원문" />
        <input class="edit-field edit-reading" data-idx="${i}" placeholder="독음" />
        <input class="edit-field edit-translation" data-idx="${i}" placeholder="해석" />
      </div>`
    )
    .join("");
  // 값은 JS로 안전하게 주입(따옴표 이스케이프 문제 회피)
  currentLines.forEach((ln, i) => {
    lyricsEl.querySelector(`.edit-original[data-idx="${i}"]`).value = ln.original || "";
    lyricsEl.querySelector(`.edit-reading[data-idx="${i}"]`).value = ln.reading || "";
    lyricsEl.querySelector(`.edit-translation[data-idx="${i}"]`).value = ln.translation || "";
  });
}

function enterEditMode() {
  if (!currentSongId) {
    alert("이 곡은 저장된 곡이 아니라 수정할 수 없어요.");
    return;
  }
  renderLyricsEdit();
}

async function saveEdits() {
  if (!currentSongId) return;
  const newLines = currentLines.map((ln, i) => ({
    original: lyricsEl.querySelector(`.edit-original[data-idx="${i}"]`)?.value ?? ln.original,
    reading: lyricsEl.querySelector(`.edit-reading[data-idx="${i}"]`)?.value ?? ln.reading,
    translation: lyricsEl.querySelector(`.edit-translation[data-idx="${i}"]`)?.value ?? ln.translation,
  }));
  editSaveBtn.disabled = true;
  try {
    const res = await fetch(`/api/library/${currentSongId}/lines`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lines: newLines }),
    });
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      alert("저장 실패: " + (d.detail || res.status));
      return;
    }
    // start 보존하며 화면 데이터 갱신
    currentLines = currentLines.map((ln, i) => ({ ...ln, ...newLines[i] }));
    renderLyricsNormal();
  } catch (err) {
    alert("저장 오류: " + err.message);
  } finally {
    editSaveBtn.disabled = false;
  }
}

// 반복 가사 등으로 시작시간이 같거나 역행하면 카라오케가 다음 줄로 못 넘어간다.
// -> 각 줄이 '구별되는, 증가하는' 시작시간을 갖도록 보정한다.
//    같은 값이 연속되면 다음 더 큰 값(또는 끝)까지 균등 분배한다.
function makeIncreasing(rawStarts) {
  const n = rawStarts.length;
  const s = rawStarts.map((x) => (typeof x === "number" && !isNaN(x) ? x : null));
  for (let i = 0; i < n; i++) {
    if (s[i] == null) s[i] = i === 0 ? 0 : s[i - 1];
  }
  let i = 1;
  while (i < n) {
    if (s[i] > s[i - 1]) { i++; continue; }
    // i 부터 시작시간이 증가하지 않음 -> 다음으로 더 큰 값(s[j])을 찾아 그 사이를 균등 분배
    let j = i;
    while (j < n && s[j] <= s[i - 1]) j++;
    const lo = s[i - 1];
    const hi = j < n ? s[j] : lo + (j - (i - 1)) * 1.2;
    const span = hi > lo ? hi - lo : (j - (i - 1)) * 0.5;
    const step = span / (j - (i - 1));
    for (let k = i; k < j; k++) {
      s[k] = +(lo + step * (k - (i - 1))).toFixed(2);
    }
    i = j < n ? j + 1 : j;
  }
  return s;
}

// --- 노래방 싱크 ---
audioEl.addEventListener("timeupdate", () => {
  if (!karaokeToggle.checked || lineStarts.length === 0) return;
  const t = audioEl.currentTime;

  // 현재 시각 이하인 '마지막' 줄을 찾는다(오프셋 반영). 전체를 훑어 순서 꼬임에도 견고.
  let idx = -1;
  for (let i = 0; i < lineStarts.length; i++) {
    const s = effectiveStart(i);
    if (s != null && s <= t) idx = i;
  }

  if (idx !== activeIdx) {
    if (activeIdx >= 0 && lineEls[activeIdx]) lineEls[activeIdx].classList.remove("active");
    activeIdx = idx;
    if (idx >= 0 && lineEls[idx]) {
      lineEls[idx].classList.add("active");
      lineEls[idx].scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }
});

karaokeToggle.addEventListener("change", () => {
  if (!karaokeToggle.checked && activeIdx >= 0 && lineEls[activeIdx]) {
    lineEls[activeIdx].classList.remove("active");
    activeIdx = -1;
  }
});

// --- 커스텀 오디오 플레이어 ---
function fmtTime(sec) {
  if (!isFinite(sec) || sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function paintRange(el, pct) {
  el.style.background =
    `linear-gradient(90deg, var(--accent) 0%, var(--accent2) ${pct}%, rgba(255,255,255,0.12) ${pct}%)`;
}

let seeking = false;

playBtn.addEventListener("click", () => {
  if (audioEl.paused) audioEl.play();
  else audioEl.pause();
});
audioEl.addEventListener("play", () => { playBtn.textContent = "❚❚"; });
audioEl.addEventListener("pause", () => { playBtn.textContent = "▶"; });
audioEl.addEventListener("ended", () => { playBtn.textContent = "▶"; });

audioEl.addEventListener("loadedmetadata", () => {
  durTimeEl.textContent = fmtTime(audioEl.duration);
  seekBar.value = 0;
  paintRange(seekBar, 0);
  curTimeEl.textContent = "0:00";
});

audioEl.addEventListener("timeupdate", () => {
  if (seeking || !isFinite(audioEl.duration)) return;
  const pct = (audioEl.currentTime / audioEl.duration) * 100;
  seekBar.value = pct;
  paintRange(seekBar, pct);
  curTimeEl.textContent = fmtTime(audioEl.currentTime);
});

seekBar.addEventListener("input", () => {
  seeking = true;
  paintRange(seekBar, parseFloat(seekBar.value));
  if (isFinite(audioEl.duration)) {
    curTimeEl.textContent = fmtTime((seekBar.value / 100) * audioEl.duration);
  }
});
seekBar.addEventListener("change", () => {
  if (isFinite(audioEl.duration)) {
    audioEl.currentTime = (seekBar.value / 100) * audioEl.duration;
  }
  seeking = false;
});

muteBtn.addEventListener("click", () => {
  audioEl.muted = !audioEl.muted;
  muteBtn.textContent = audioEl.muted || audioEl.volume === 0 ? "🔇" : "🔊";
});
volBar.addEventListener("input", () => {
  audioEl.muted = false;
  audioEl.volume = parseFloat(volBar.value);
  paintRange(volBar, volBar.value * 100);
  muteBtn.textContent = audioEl.volume === 0 ? "🔇" : "🔊";
});
paintRange(volBar, 100);

// --- 저장된 노래(라이브러리) ---
function openLibrary() {
  libraryOverlay.classList.remove("hidden");
  loadLibraryList();
}
function closeLibrary() {
  libraryOverlay.classList.add("hidden");
}

async function loadLibraryList() {
  libraryList.innerHTML = '<div class="library-empty">불러오는 중…</div>';
  try {
    const res = await fetch("/api/library");
    const songs = await res.json();
    if (!songs.length) {
      libraryList.innerHTML =
        '<div class="library-empty">아직 저장된 노래가 없어요.<br/>곡을 변환하면 자동으로 저장됩니다.</div>';
      return;
    }
    libraryList.innerHTML = songs
      .map(
        (s) => `
        <div class="library-item" data-id="${s.id}">
          <div class="library-item-info">
            <div class="library-item-title">${escapeHtml(s.title)}</div>
            <div class="library-item-artist">${escapeHtml(s.artist)}</div>
            <div class="library-item-date">${escapeHtml((s.created || "").replace("T", " "))}</div>
          </div>
          <button class="library-item-del" data-del="${s.id}" title="이 노래 삭제">🗑 삭제</button>
        </div>`
      )
      .join("");
  } catch (err) {
    libraryList.innerHTML = `<div class="library-empty">목록을 불러오지 못했습니다: ${escapeHtml(err.message)}</div>`;
  }
}

async function loadSavedSong(id) {
  showStatus('<span class="spinner"></span> 저장된 노래 불러오는 중…');
  closeLibrary();
  resultEl.classList.add("hidden");
  try {
    const res = await fetch(`/api/library/${id}`);
    const data = await res.json();
    if (!res.ok) {
      showStatus("❌ " + (data.detail || "불러오기 실패"), true);
      return;
    }
    hideStatus();
    if (data.url) urlInput.value = data.url;
    renderResult(data);
  } catch (err) {
    showStatus("❌ 네트워크 오류: " + err.message, true);
  }
}

async function deleteSavedSong(id, title) {
  if (!confirm(`'${title || "이 노래"}'를 저장 목록에서 삭제할까요?`)) return;
  try {
    await fetch(`/api/library/${id}`, { method: "DELETE" });
  } catch {}
  loadLibraryList();
}

async function clearAllSongs() {
  if (!confirm("저장된 노래를 모두 삭제할까요? 되돌릴 수 없습니다.")) return;
  try {
    await fetch("/api/library", { method: "DELETE" });
  } catch {}
  loadLibraryList();
}

libraryBtn.addEventListener("click", openLibrary);
libraryClose.addEventListener("click", closeLibrary);
libraryClearAll.addEventListener("click", clearAllSongs);
libraryOverlay.addEventListener("click", (e) => {
  if (e.target === libraryOverlay) closeLibrary();
});
libraryList.addEventListener("click", (e) => {
  const del = e.target.closest("[data-del]");
  if (del) {
    e.stopPropagation();
    const item = del.closest(".library-item");
    const title = item?.querySelector(".library-item-title")?.textContent || "";
    deleteSavedSong(del.dataset.del, title);
    return;
  }
  const item = e.target.closest(".library-item");
  if (item) loadSavedSong(item.dataset.id);
});

// --- 가사 복사 ---
function buildCopyText(mode) {
  if (!currentLines.length) return "";
  if (mode === "original") return currentLines.map((l) => l.original || "").join("\n");
  if (mode === "reading") return currentLines.map((l) => l.reading || "").join("\n");
  if (mode === "translation") return currentLines.map((l) => l.translation || "").join("\n");
  // all: 원문 / 독음 / 해석을 묶어서, 줄 사이 빈 줄
  return currentLines
    .map((l) =>
      [l.original, l.reading, l.translation].filter((s) => s && s.trim()).join("\n")
    )
    .join("\n\n");
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // 보안 컨텍스트가 아닐 때 폴백
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch {
      ok = false;
    }
    document.body.removeChild(ta);
    return ok;
  }
}

let copyMode = "all"; // 선택된 복사 범위(토글)
let feedbackTimer = null;

// 복사 범위 토글(전체/원문/독음/해석 중 하나 선택)
copyModeToggle.addEventListener("click", (e) => {
  const btn = e.target.closest(".seg-btn[data-copy]");
  if (!btn) return;
  copyMode = btn.dataset.copy;
  copyModeToggle.querySelectorAll(".seg-btn").forEach((b) =>
    b.classList.toggle("active", b === btn)
  );
});

// 선택된 범위 복사
copyBtn.addEventListener("click", async () => {
  const text = buildCopyText(copyMode);
  if (!text) return;
  const ok = await copyText(text);
  const labels = { all: "전체", original: "원문", reading: "독음", translation: "해석" };
  copyFeedback.textContent = ok ? `✓ ${labels[copyMode]} 복사됨` : "복사 실패";
  copyFeedback.classList.toggle("error", !ok);
  clearTimeout(feedbackTimer);
  feedbackTimer = setTimeout(() => (copyFeedback.textContent = ""), 2000);
});

// --- 가사만 보기(새 창) ---
function openLyricsWindow() {
  if (!currentLines.length) return;
  const rows = currentLines
    .map(
      (l) => `
      <div class="line">
        <div class="o">${escapeHtml(l.original)}</div>
        <div class="r">${escapeHtml(l.reading)}</div>
        <div class="t">${escapeHtml(l.translation)}</div>
      </div>`
    )
    .join("");
  const html = `<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${escapeHtml(currentTitle)} - 가사</title>
  <style>
    :root { --bg:#13131f; --card:#1a1b2e; --text:#eaeaf2; --muted:#9a9ab0; --line:#2a2b45; --accent:#ff5d8f; }
    * { box-sizing: border-box; }
    body { margin:0; background:var(--bg); color:var(--text);
      font-family:"Segoe UI","Malgun Gothic",system-ui,sans-serif; padding:28px 18px 60px; }
    .wrap { max-width:640px; margin:0 auto; }
    header { margin-bottom:20px; }
    h1 { margin:0 0 4px; font-size:1.5rem; }
    .artist { color:var(--muted); font-size:0.95rem; }
    .line { padding:12px 4px; border-bottom:1px solid var(--line); }
    .o { font-size:1.12rem; font-weight:600; }
    .r { color:#ffb3c8; font-size:0.95rem; margin-top:3px; }
    .t { color:var(--muted); font-size:0.92rem; margin-top:3px; }
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>${escapeHtml(currentTitle)}</h1>
      <div class="artist">${escapeHtml(currentArtist)}</div>
    </header>
    ${rows}
  </div>
</body>
</html>`;
  // Blob URL로 실제 페이지를 연다(내장 브라우저에서도 안정적으로 렌더됨).
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const w = window.open(url, "_blank", "width=560,height=760,scrollbars=yes,resizable=yes");
  if (!w) {
    URL.revokeObjectURL(url);
    alert("팝업이 차단되었어요. 브라우저에서 이 사이트의 팝업을 허용해 주세요.");
    return;
  }
  // 로드 후 URL 정리
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

lyricsOnlyBtn.addEventListener("click", openLyricsWindow);

// --- 가사 수정 ---
editBtn.addEventListener("click", () => {
  if (editMode) renderLyricsNormal();
  else enterEditMode();
});
editSaveBtn.addEventListener("click", saveEdits);
editCancelBtn.addEventListener("click", renderLyricsNormal);

function escapeHtml(s) {
  return (s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
