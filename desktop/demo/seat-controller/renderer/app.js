/**
 * 座椅控制器 — 渲染进程逻辑
 *
 * 纯前端状态机 + SVG 姿态映射；记忆位置通过 preload 暴露的 seatStore 持久化。
 */

const POSE_KEYS = ['backrest', 'slide', 'height', 'legRest', 'headrest'];

const RANGES = {
  backrest: { min: 90, max: 160, unit: '°' },
  slide: { min: 0, max: 100, unit: '%' },
  height: { min: 0, max: 100, unit: '%' },
  legRest: { min: 0, max: 70, unit: '°' },
  headrest: { min: 0, max: 100, unit: '%' },
};

const DEFAULTS = {
  backrest: 105,
  slide: 45,
  height: 50,
  legRest: 0,
  headrest: 50,
  heat: 0,
  vent: 0,
  massage: 'off',
  massageLevel: 1,
  memory: [null, null, null],
};

const HEAT_LABELS = ['关闭', '低档', '中档', '高档'];
const VENT_LABELS = ['关闭', '低档', '中档', '高档'];
const MASSAGE_LABELS = { off: '关闭', wave: '波浪', pulse: '脉冲', lumbar: '腰部' };

const $ = (id) => document.getElementById(id);

const svg = $('seatSvg');
const seatRoot = $('seatRoot');
const backrestGroup = $('backrestGroup');
const headrestGroup = $('headrestGroup');
const legRestGroup = $('legRestGroup');

/** @type {typeof DEFAULTS} */
let state = structuredClone(DEFAULTS);
let saveTimer = null;

// ─── 工具 ────────────────────────────────────────────

function clamp(value, min, max) {
  const n = Number(value);
  if (!Number.isFinite(n)) return min;
  return Math.min(max, Math.max(min, Math.round(n)));
}

function sanitizePose(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const pose = {};
  for (const key of POSE_KEYS) {
    pose[key] = clamp(raw[key], RANGES[key].min, RANGES[key].max);
  }
  return pose;
}

function normalize(raw) {
  const source = raw && typeof raw === 'object' ? raw : {};
  const next = { ...DEFAULTS };

  for (const key of POSE_KEYS) {
    next[key] = clamp(source[key] ?? DEFAULTS[key], RANGES[key].min, RANGES[key].max);
  }
  next.heat = clamp(source.heat ?? DEFAULTS.heat, 0, 3);
  next.vent = clamp(source.vent ?? DEFAULTS.vent, 0, 3);
  next.massage = ['off', 'wave', 'pulse', 'lumbar'].includes(source.massage)
    ? source.massage
    : 'off';
  next.massageLevel = clamp(source.massageLevel ?? DEFAULTS.massageLevel, 1, 3);
  next.memory = [0, 1, 2].map((i) =>
    Array.isArray(source.memory) ? sanitizePose(source.memory[i]) : null
  );

  return next;
}

function poseOf(source) {
  const pose = {};
  for (const key of POSE_KEYS) {
    pose[key] = source[key];
  }
  return pose;
}

let toastTimer = null;

function showToast(message) {
  const toast = $('toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 1800);
}

function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    try {
      await window.seatStore?.save(state);
    } catch (err) {
      console.error('[SeatController] 状态保存失败:', err);
    }
  }, 350);
}

// ─── 渲染 ────────────────────────────────────────────

function renderPose() {
  for (const key of POSE_KEYS) {
    const input = $(key);
    const output = $(`${key}Val`);
    const { unit } = RANGES[key];
    input.value = String(state[key]);
    output.textContent = `${state[key]}${unit}`;
  }

  // 滑动 + 升降：整体平移
  const dx = ((state.slide - 50) * 0.6).toFixed(1);
  const dy = ((50 - state.height) * 0.55).toFixed(1);
  seatRoot.setAttribute('transform', `translate(${dx} ${dy})`);

  // 靠背：90° 直立，角度越大越向后倾（视觉映射到 0°~-45°，保证完整可见）
  const tilt = -((state.backrest - 90) * 0.64).toFixed(1);
  backrestGroup.setAttribute('transform', `rotate(${tilt} 131 312)`);

  // 头枕：沿靠背上下平移
  const headOffset = ((50 - state.headrest) * 0.26).toFixed(1);
  headrestGroup.setAttribute('transform', `translate(0 ${headOffset})`);

  // 腿托：以座垫前缘为轴展开
  legRestGroup.setAttribute('transform', `rotate(${state.legRest} 288 300)`);

  // 顶部与遥测读数
  $('hudBackrest').textContent = `${state.backrest}°`;
  $('tBackrest').textContent = `${state.backrest}°`;
  $('tLegRest').textContent = `${state.legRest}°`;
  $('tSlide').textContent = `${state.slide}%`;
  $('tHeight').textContent = `${state.height}%`;
  $('tHeadrest').textContent = `${state.headrest}%`;
}

function renderComfort() {
  const heatRatio = state.heat / 3;
  $('heatBack').setAttribute('opacity', (heatRatio * 0.42).toFixed(2));
  $('heatSeat').setAttribute('opacity', (heatRatio * 0.42).toFixed(2));
  $('heatLeg').setAttribute('opacity', (heatRatio * 0.3).toFixed(2));

  const venting = state.vent > 0;
  for (const id of ['ventBack', 'ventSeat']) {
    const group = $(id);
    group.setAttribute('opacity', venting ? '0.9' : '0');
    group.classList.toggle('venting', venting);
    group.querySelectorAll('path').forEach((path) => {
      path.style.animationDuration = `${(1.05 - state.vent * 0.16).toFixed(2)}s`;
    });
  }

  const massaging = state.massage !== 'off';
  svg.dataset.massage = state.massage;
  const massageGroup = $('massageBack');
  massageGroup.setAttribute('opacity', massaging ? '0.92' : '0');
  massageGroup.querySelectorAll('circle').forEach((circle) => {
    circle.style.animationDuration = `${(1.6 - state.massageLevel * 0.22).toFixed(2)}s`;
  });

  $('heatVal').textContent = HEAT_LABELS[state.heat];
  $('ventVal').textContent = VENT_LABELS[state.vent];
  $('massageVal').textContent = MASSAGE_LABELS[state.massage];
  $('massageLevel').value = String(state.massageLevel);
  $('massageLevel').disabled = !massaging;
  $('massageLevelVal').textContent = `${state.massageLevel} 档`;

  document.querySelectorAll('.seg').forEach((seg) => {
    const func = seg.dataset.func;
    seg.querySelectorAll('button').forEach((btn) => {
      const value = func === 'massage' ? btn.dataset.value : Number(btn.dataset.value);
      btn.classList.toggle('active', value === state[func]);
      btn.setAttribute('aria-pressed', String(value === state[func]));
    });
  });
}

function renderMemory() {
  document.querySelectorAll('.mem').forEach((card) => {
    const slot = Number(card.dataset.slot);
    const saved = Boolean(state.memory[slot]);
    card.classList.toggle('saved', saved);
    card.querySelector('.memRecall').disabled = !saved;
  });
}

function render() {
  renderPose();
  renderComfort();
  renderMemory();
}

// ─── 交互 ────────────────────────────────────────────

function bindSliders() {
  for (const key of POSE_KEYS) {
    $(key).addEventListener('input', (event) => {
      state[key] = clamp(event.target.value, RANGES[key].min, RANGES[key].max);
      renderPose();
      scheduleSave();
    });
  }

  $('massageLevel').addEventListener('input', (event) => {
    state.massageLevel = clamp(event.target.value, 1, 3);
    renderComfort();
    scheduleSave();
  });
}

function bindSegments() {
  document.querySelectorAll('.seg').forEach((seg) => {
    seg.addEventListener('click', (event) => {
      const btn = event.target.closest('button');
      if (!btn) return;

      const func = seg.dataset.func;
      if (func === 'massage') {
        state.massage = btn.dataset.value;
        showToast(`按摩模式：${MASSAGE_LABELS[state.massage]}`);
      } else {
        state[func] = Number(btn.dataset.value);
        const labels = func === 'heat' ? HEAT_LABELS : VENT_LABELS;
        showToast(`${func === 'heat' ? '座椅加热' : '座椅通风'}：${labels[state[func]]}`);
      }

      renderComfort();
      scheduleSave();
    });
  });
}

function bindMemory() {
  document.querySelectorAll('.mem').forEach((card) => {
    const slot = Number(card.dataset.slot);
    const name = `M${slot + 1}`;

    card.querySelector('.memSave').addEventListener('click', () => {
      state.memory[slot] = poseOf(state);
      renderMemory();
      scheduleSave();
      showToast(`当前姿态已保存到 ${name}`);
    });

    card.querySelector('.memRecall').addEventListener('click', () => {
      recall(slot);
    });
  });
}

function recall(slot) {
  const pose = state.memory[slot];
  if (!pose) {
    showToast(`M${slot + 1} 尚未保存`);
    return;
  }
  Object.assign(state, pose);
  renderPose();
  scheduleSave();
  showToast(`已调用记忆位置 M${slot + 1}`);
}

function bindGlobal() {
  $('resetBtn').addEventListener('click', () => {
    for (const key of POSE_KEYS) {
      state[key] = DEFAULTS[key];
    }
    state.heat = DEFAULTS.heat;
    state.vent = DEFAULTS.vent;
    state.massage = DEFAULTS.massage;
    state.massageLevel = DEFAULTS.massageLevel;
    render();
    scheduleSave();
    showToast('座椅已复位到默认姿态');
  });

  window.addEventListener('keydown', (event) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (/^(INPUT|TEXTAREA)$/.test(event.target.tagName)) return;

    const slot = ['1', '2', '3'].indexOf(event.key);
    if (slot >= 0) {
      recall(slot);
    }
  });
}

// ─── 启动 ────────────────────────────────────────────

async function init() {
  bindSliders();
  bindSegments();
  bindMemory();
  bindGlobal();

  let stored = null;
  try {
    stored = await window.seatStore?.load();
  } catch (err) {
    console.error('[SeatController] 状态读取失败:', err);
  }

  state = normalize(stored);
  render();

  if (stored) {
    showToast('已恢复上次座椅姿态');
  }
}

init();
