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
  if (resp.status === 204) return null;
  return resp.json();
}

const api = {
  // ── Exercises ──────────────────────────────────────────────────────────────
  getExercises:          ()          => apiFetch('/exercises'),
  getExercise:           (id)        => apiFetch(`/exercises/${id}`),
  getExerciseHistory:    (id, n=10)  => apiFetch(`/exercises/${id}/history?limit=${n}`),
  getExerciseLastWorkout:(id)        => apiFetch(`/exercises/${id}/last-workout`),
  getExerciseTip:        (id)        => apiFetch(`/exercises/${id}/tip`, { method:'POST' }),
  createExercise: (data) => apiFetch('/exercises', { method:'POST', body:JSON.stringify(data) }),
  detectMachine:  (b64)  => apiFetch('/exercises/detect', { method:'POST', body:JSON.stringify({image_base64:b64}) }),
  identifyExercise:(data)=> apiFetch('/exercises/identify', { method:'POST', body:JSON.stringify(data) }),
  getExerciseLibrary(muscle, search) {
    const p = new URLSearchParams();
    if (muscle) p.set('muscle', muscle);
    if (search) p.set('search', search);
    const q = p.toString();
    return apiFetch(`/exercise-library${q ? '?'+q : ''}`);
  },

  // ── Workouts ───────────────────────────────────────────────────────────────
  getWorkouts:    (params={}) => { const q = new URLSearchParams(params).toString(); return apiFetch(`/workouts${q?'?'+q:''}`); },
  createWorkout:  (data) => apiFetch('/workouts', { method:'POST', body:JSON.stringify(data) }),
  getWorkout:     (id)   => apiFetch(`/workouts/${id}`),
  deleteWorkout:  (id)   => apiFetch(`/workouts/${id}`, { method:'DELETE' }),

  // ── Workout exercises ──────────────────────────────────────────────────────
  addExerciseToWorkout:     (wId,eId) => apiFetch(`/workouts/${wId}/exercises`, { method:'POST', body:JSON.stringify({exercise_id:eId}) }),
  removeExerciseFromWorkout:(weId)    => apiFetch(`/workout-exercises/${weId}`, { method:'DELETE' }),

  // ── Sets ───────────────────────────────────────────────────────────────────
  addSet:    (weId,r,w) => apiFetch(`/workout-exercises/${weId}/sets`, { method:'POST', body:JSON.stringify({reps:r,weight_kg:w}) }),
  updateSet: (id,r,w)   => apiFetch(`/sets/${id}`, { method:'PUT',  body:JSON.stringify({reps:r,weight_kg:w}) }),
  deleteSet: (id)       => apiFetch(`/sets/${id}`, { method:'DELETE' }),

  // ── Legacy ─────────────────────────────────────────────────────────────────
  createSession:   (data) => apiFetch('/sessions', { method:'POST', body:JSON.stringify(data) }),
  getHistory:      (name) => apiFetch(`/sessions/${encodeURIComponent(name)}`),
  getWeeklySummary:()     => apiFetch('/weekly-summary'),
};

// ── Utilities ─────────────────────────────────────────────────────────────────

function showToast(msg, type = 'success') {
  const el = document.createElement('div');
  el.className = [
    'fixed top-4 left-4 right-4 z-[100] py-3 px-4 rounded-xl text-center',
    'text-white font-semibold text-sm shadow-lg pointer-events-none',
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
  if (on) btn._origHTML = btn.innerHTML;
  btn.disabled = on;
  if (on) {
    btn.innerHTML = '<span class="opacity-60">Chargement…</span>';
  } else if (btn._origHTML !== undefined) {
    btn.innerHTML = btn._origHTML;
  }
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

function daysAgo(dateStr) {
  if (!dateStr) return '';
  const diff = Math.floor((Date.now() - new Date(dateStr + 'T12:00:00').getTime()) / 86400000);
  if (diff <= 0) return "aujourd'hui";
  if (diff === 1) return 'hier';
  return `il y a ${diff}j`;
}

// Muscle → Tailwind color classes
const _MUSCLE_COLORS = [
  [['pec','chest'],          'bg-orange-500/20 text-orange-400 border-orange-500/30'],
  [['bicep'],                'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'],
  [['dos','back','lats'],    'bg-blue-500/20   text-blue-400   border-blue-500/30'  ],
  [['tricep'],               'bg-cyan-500/20   text-cyan-400   border-cyan-500/30'  ],
  [['épaul','delt','should'],'bg-purple-500/20 text-purple-400 border-purple-500/30'],
  [['mollet','calf','calv'], 'bg-teal-500/20   text-teal-400   border-teal-500/30'  ],
  [['quad','thigh'],         'bg-green-500/20  text-green-400  border-green-500/30' ],
  [['ischio','hamstr','fess','glut'],'bg-lime-500/20 text-lime-400 border-lime-500/30'],
  [['abdo','core','abs'],    'bg-red-500/20    text-red-400    border-red-500/30'   ],
  [['cardio'],               'bg-pink-500/20   text-pink-400   border-pink-500/30'  ],
];

function getMuscleColor(muscle) {
  const m = (muscle || '').toLowerCase();
  for (const [keys, cls] of _MUSCLE_COLORS) {
    if (keys.some(k => m.includes(k))) return cls;
  }
  return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
}

function muscleBadge(muscle) {
  return `<span class="inline-block text-[11px] font-semibold px-1.5 py-0.5 rounded-full border ${getMuscleColor(muscle)}">${escapeHtml(muscle)}</span>`;
}

// ── Shared nav HTML ───────────────────────────────────────────────────────────
// Each page inlines the nav with its own active tab highlighted — see each file.
