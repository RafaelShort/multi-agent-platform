import axios from "axios";

const client = axios.create({
  baseURL: "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
});

export async function sendChat(
  messages,
  { temperature = 0.7, maxTokens = 512, capability = "chat", system = null } = {}
) {
  const { data } = await client.post("/api/chat", {
    messages,
    temperature,
    max_tokens: maxTokens,
    capability,
    system,
  });
  return data;
}

export async function getAgents() {
  const { data } = await client.get("/api/agents");
  return data;
}

export async function getStats() {
  const { data } = await client.get("/api/stats");
  return data;
}

export async function getHealth() {
  const { data } = await client.get("/api/health");
  return data;
}
