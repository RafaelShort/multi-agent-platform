// personaStore.js — overrides de persona persistidos no navegador.
const KEY = "persona_overrides_v1";

export function loadOverrides() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || {};
  } catch {
    return {};
  }
}

export function saveOverride(id, data) {
  const all = loadOverrides();
  all[id] = data; // { name, emoji, system, temperature }
  localStorage.setItem(KEY, JSON.stringify(all));
}

export function clearOverride(id) {
  const all = loadOverrides();
  delete all[id];
  localStorage.setItem(KEY, JSON.stringify(all));
}

// Junta defaults do backend com overrides locais.
export function mergePersonas(backendAgents, overrides) {
  return backendAgents.map((a) => {
    const o = overrides[a.agent_id];
    return o
      ? { ...a, ...o, customized: true }
      : { ...a, customized: false };
  });
}
