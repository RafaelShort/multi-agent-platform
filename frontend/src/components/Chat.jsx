import { useEffect, useRef, useState } from "react";
import { sendChat, getAgents } from "../api";
import { loadOverrides, saveOverride, clearOverride, mergePersonas } from "../personaStore";
import PersonaEditor from "./PersonaEditor";

function Bubble({ msg, personaById }) {
  const isUser = msg.role === "user";
  const p = personaById[msg.agent_id];
  const label = p ? `${p.emoji} ${p.name}` : `🤖 ${msg.agent_id || "assistant"}`;
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap shadow-sm
          ${isUser
            ? "bg-blue-600 text-white rounded-br-sm"
            : "bg-gray-800 text-gray-100 border border-gray-700 rounded-bl-sm"}`}
      >
        {!isUser && (
          <div className="text-[10px] text-blue-400 mb-1 font-medium">{label}</div>
        )}
        {msg.content}
        {!isUser && msg.meta && (
          <div className="text-[10px] text-gray-500 mt-1.5">
            {msg.meta.tokens} tokens · {Math.round(msg.meta.latency)}ms
          </div>
        )}
      </div>
    </div>
  );
}

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [backendAgents, setBackendAgents] = useState([]);
  const [overrides, setOverrides] = useState(loadOverrides());
  const [target, setTarget] = useState("chat");
  const [editing, setEditing] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    getAgents().then(setBackendAgents).catch(() => setBackendAgents([]));
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const agents = mergePersonas(backendAgents, overrides);
  const personaById = Object.fromEntries(agents.map((a) => [a.agent_id, a]));
  const selected = personaById[target];

  function handleSaveOverride(data) {
    saveOverride(target, data);
    setOverrides(loadOverrides());
    setEditing(false);
  }

  function handleResetOverride() {
    clearOverride(target);
    setOverrides(loadOverrides());
    setEditing(false);
  }

  async function handleSend(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    const userMsg = { role: "user", content: text };
    const history = [...messages, userMsg];
    setMessages(history);
    setInput("");
    setLoading(true);

    try {
      const payload = history.map(({ role, content }) => ({ role, content }));
      const res = await sendChat(payload, {
        temperature: selected ? selected.temperature : 0.7,
        maxTokens: 512,
        capability: target,
        system: selected ? selected.system : null,
      });

      if (res.status === "completed") {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: res.content,
            agent_id: res.agent_id,
            meta: { tokens: res.total_tokens, latency: res.latency_ms },
          },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `⚠️ ${res.status}: ${res.error || "falhou"}` },
        ]);
      }
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `⚠️ Erro de conexão: ${err.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex-1 flex flex-col bg-gray-950">
      <header className="px-6 py-4 border-b border-gray-800 bg-gray-900">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-semibold text-gray-100">Chat com LLM</h2>
            <p className="text-xs text-gray-500">llama3.2 via Ollama · contexto multi-turn</p>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs text-gray-400">Especialista:</label>
            <select
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              className="bg-gray-800 border border-gray-700 text-gray-100 text-sm
                rounded-lg px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="chat">🔀 Auto (round-robin)</option>
              {agents.map((a) => (
                <option key={a.agent_id} value={a.agent_id}>
                  {a.emoji} {a.name}{a.customized ? " ●" : ""}
                </option>
              ))}
            </select>
            <button
              onClick={() => setEditing(true)}
              disabled={!selected}
              title={selected ? "Editar personalidade" : "Selecione um especialista"}
              className="text-sm rounded-lg px-3 py-1.5 bg-gray-800 border border-gray-700
                text-gray-200 hover:bg-gray-700 disabled:opacity-40 transition"
            >
              ⚙️
            </button>
          </div>
        </div>
        {selected && (
          <p className="text-xs text-gray-400 mt-2 italic">
            {selected.emoji} {selected.name} — {selected.description || "personalizado"}
            <span className="text-gray-600"> (temp {Number(selected.temperature).toFixed(1)})</span>
          </p>
        )}
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
        {messages.map((m, i) => (
          <Bubble key={i} msg={m} personaById={personaById} />
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-800 border border-gray-700 rounded-2xl px-4 py-2.5 text-sm text-gray-400">
              <span className="animate-pulse">🤖 pensando...</span>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={handleSend}
        className="p-4 border-t border-gray-800 bg-gray-900 flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            selected ? `Falando com ${selected.name}...` : "Digite (modo automatico)..."
          }
          disabled={loading}
          className="flex-1 rounded-full bg-gray-800 border border-gray-700 text-gray-100
            placeholder-gray-500 px-4 py-2.5 text-sm
            focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-full bg-blue-600 text-white px-5 py-2.5 text-sm font-medium
            hover:bg-blue-700 disabled:opacity-40 transition"
        >
          Enviar
        </button>
      </form>

      {editing && selected && (
        <PersonaEditor
          persona={selected}
          onSave={handleSaveOverride}
          onReset={handleResetOverride}
          onClose={() => setEditing(false)}
        />
      )}
    </main>
  );
}
