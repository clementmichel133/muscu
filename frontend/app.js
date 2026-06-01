const API_BASE = '';

async function apiFetch(path, options = {}) {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `Erreur HTTP ${resp.status}`);
  }
  return resp.json();
}

const api = {
  getExercises: () => apiFetch('/exercises'),

  createExercise: (data) => apiFetch('/exercises', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  detectMachine: (image_base64) => apiFetch('/exercises/detect', {
    method: 'POST',
    body: JSON.stringify({ image_base64 }),
  }),

  createSession: (data) => apiFetch('/sessions', {
    method: 'POST',
    body: JSON.stringify(data),
  }),

  getHistory: (exerciseName) =>
    apiFetch(`/sessions/${encodeURIComponent(exerciseName)}`),

  getWeeklySummary: () => apiFetch('/weekly-summary'),
};

function showToast(msg, type = 'success') {
  const el = document.createElement('div');
  el.className = [
    'fixed top-4 left-4 right-4 z-[100] py-3 px-4 rounded-xl text-center',
    'text-white font-semibold text-sm shadow-lg',
    type === 'success' ? 'bg-green-600' : 'bg-red-600',
  ].join(' ');
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => {
    el.style.transition = 'opacity 300ms';
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 320);
  }, 2500);
}

function setLoading(btn, on) {
  if (!btn._orig) btn._orig = btn.textContent;
  btn.disabled = on;
  btn.textContent = on ? 'Chargement…' : btn._orig;
  btn.classList.toggle('opacity-60', on);
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = String(str ?? '');
  return d.innerHTML;
}
