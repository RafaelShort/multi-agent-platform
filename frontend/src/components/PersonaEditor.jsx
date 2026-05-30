import { useState } from "react";

export default function PersonaEditor({ persona, onSave, onReset, onClose }) {
  const [name, setName] = useState(persona.name);
  const [emoji, setEmoji] = useState(persona.emoji);
  const [system, setSystem] = useState(persona.system || "");
  const [temperature, setTemperature] = useState(persona.temperature ?? 0.7);

  function handleSave() {
    onSave({
      name: name.trim() || persona.name,
      emoji: emoji.trim() || "🤖",
      system: system.trim(),
      temperature: Number(temperature),
    });
  }

  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-gray-100 font-semibold">
            Configurar personalidade
            {persona.customized && (
              <span className="ml-2 text-[10px] text-amber-400 align-middle">
                ● personalizado
              </span>
            )}
          </h3>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-200 text-xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="flex gap-3 mb-4">
          <div className="w-20">
            <label className="text-xs text-gray-400">Emoji</label>
            <input
              value={emoji}
              onChange={(e) => setEmoji(e.target.value)}
              className="w-full mt-1 bg-gray-800 border border-gray-700 text-gray-100
                rounded-lg px-3 py-2 text-center text-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="flex-1">
            <label className="text-xs text-gray-400">Nome</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full mt-1 bg-gray-800 border border-gray-700 text-gray-100
                rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        <div className="mb-4">
          <label className="text-xs text-gray-400">
            Personalidade (system prompt)
          </label>
          <textarea
            value={system}
            onChange={(e) => setSystem(e.target.value)}
            rows={6}
            placeholder="Descreva como este agente deve se comportar..."
            className="w-full mt-1 bg-gray-800 border border-gray-700 text-gray-100
              rounded-lg px-3 py-2 text-sm resize-none
              focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div className="mb-6">
          <label className="text-xs text-gray-400 flex justify-between">
            <span>Criatividade</span>
            <span className="text-blue-400 font-medium">{Number(temperature).toFixed(1)}</span>
          </label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={temperature}
            onChange={(e) => setTemperature(e.target.value)}
            className="w-full mt-2 accent-blue-500"
          />
          <div className="flex justify-between text-[10px] text-gray-600 mt-1">
            <span>0 · preciso</span>
            <span>1 · criativo</span>
          </div>
        </div>

        <div className="flex justify-between items-center">
          <button
            onClick={onReset}
            className="text-xs text-gray-400 hover:text-red-400 transition"
          >
            ↺ Restaurar padrao
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-300 hover:text-white"
            >
              Cancelar
            </button>
            <button
              onClick={handleSave}
              className="px-5 py-2 text-sm rounded-lg bg-blue-600 text-white
                hover:bg-blue-700 transition font-medium"
            >
              Salvar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
