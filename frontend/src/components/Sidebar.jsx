import { useEffect, useState } from "react";
import { getAgents, getStats, getHealth } from "../api";

function Dot({ status }) {
  const color =
    status === "idle" ? "bg-green-400"
    : status === "busy" ? "bg-yellow-400"
    : "bg-gray-500";
  return <span className={`inline-block w-2.5 h-2.5 rounded-full ${color}`} />;
}

export default function Sidebar() {
  const [agents, setAgents] = useState([]);
  const [stats, setStats] = useState(null);
  const [online, setOnline] = useState(false);

  async function refresh() {
    try {
      const h = await getHealth();
      setOnline(h.status === "ok");
      setAgents(await getAgents());
      setStats(await getStats());
    } catch {
      setOnline(false);
    }
  }

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 3000); // polling a cada 3s
    return () => clearInterval(id);
  }, []);

  return (
    <aside className="w-64 bg-gray-900 text-gray-200 flex flex-col p-4 gap-6">
      <div>
        <h1 className="text-lg font-bold flex items-center gap-2">
          🤖 Multi-Agent
        </h1>
        <p className="text-xs text-gray-400 flex items-center gap-1.5 mt-1">
          <Dot status={online ? "idle" : "off"} />
          {online ? "API online" : "API offline"}
        </p>
      </div>

      <div>
        <h2 className="text-xs uppercase tracking-wide text-gray-500 mb-2">
          Agentes
        </h2>
        <ul className="space-y-1.5">
          {agents.length === 0 && (
            <li className="text-xs text-gray-500">nenhum agente</li>
          )}
          {agents.map((a) => (
            <li key={a.agent_id} className="flex items-center gap-2 text-sm">
              <Dot status={a.status} />
              <span className="font-medium">{a.agent_id}</span>
              <span className="text-xs text-gray-500">{a.status}</span>
            </li>
          ))}
        </ul>
      </div>

      {stats && (
        <div>
          <h2 className="text-xs uppercase tracking-wide text-gray-500 mb-2">
            Stats
          </h2>
          <ul className="space-y-1 text-sm">
            <li>✅ completas: {stats.completed}</li>
            <li>⏳ pendentes: {stats.pending}</li>
            <li>📤 enviadas: {stats.submitted}</li>
            <li>❌ falhas: {stats.failed}</li>
            <li>⌛ timeouts: {stats.timeout}</li>
          </ul>
        </div>
      )}

      <div className="mt-auto text-[10px] text-gray-600">
        Ollama · llama3.2 · Kafka
      </div>
    </aside>
  );
}
