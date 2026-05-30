# 🤖 Multi-Agent Platform

> Plataforma de chat multi-agente com orquestração distribuída, agentes LLM especializados e roteamento de tarefas via Kafka.

Múltiplos agentes LLM trabalham em paralelo, coordenados por um orquestrador que distribui tarefas através de um message bus. Cada agente possui uma personalidade própria e pode ser configurado em tempo real pela interface.

---

## Visão geral

O projeto simula uma **plataforma multi-agente** onde diferentes agentes de IA, cada um com sua especialidade, atendem requisições de chat. Em vez de um único modelo, o sistema distribui o trabalho entre agentes coordenados por um orquestrador, comunicando-se de forma assíncrona via Kafka.

---

## Principais recursos

- **Múltiplos agentes especializados** — Pesquisador, Programador e Criativo, cada um com system prompt e temperatura próprios.
- **Roteamento inteligente** — modo automático ou roteamento direto para um especialista específico.
- **Editor de personalidade ao vivo** — customize nome, emoji, system prompt e criatividade de cada agente pela interface, com persistência no navegador (localStorage).
- **Contexto multi-turn** — os agentes mantêm o histórico da conversa.
- **Processamento paralelo** — múltiplas requisições são distribuídas entre os agentes simultaneamente.
- **Observabilidade** — sidebar com status dos agentes em tempo real e estatísticas do orquestrador (tarefas enviadas, completas, falhas, timeouts).
- **Interfaces** — API REST, CLI e frontend web.

---

**Fluxo de uma requisição:**

1. O cliente (frontend/CLI) envia mensagens + a `capability` desejada para a API.
2. A API cria uma `Task` e a submete ao `Orchestrator`.
3. O `Orchestrator` seleciona um agente disponível e publica a tarefa no tópico Kafka correspondente.
4. O `LLMAgent` consome a tarefa, monta o prompt (aplicando sua persona) e chama o Ollama.
5. A resposta retorna pelo bus até a API, que devolve ao cliente com metadados (agente, tokens, latência).

---

## Stack

| Camada          | Tecnologia                                       |
|-----------------|--------------------------------------------------|
| **Backend**     | Python 3.12, FastAPI, Uvicorn                    |
| **Mensageria**  | Apache Kafka (via Docker)                         |
| **LLM**         | Ollama (llama3.2) — API compatível com OpenAI    |
| **Frontend**    | React 18, Vite, TailwindCSS, Axios               |
| **Validação**   | Pydantic                                          |
| **Infra**       | Docker / Docker Compose                           |

---

## Pré-requisitos

- **Docker** e **Docker Compose** (para o Kafka)
- **Python 3.12+**
- **Node.js 18+** e **npm**
- **Ollama** instalado e em execução, com o modelo baixado:

```bash
ollama pull llama3.2:latest
```

---

## Instalação e execução

> Os comandos abaixo usam PowerShell (Windows). Em Linux/macOS, ajuste a ativação do venv para `source .venv/bin/activate`.

### 1. Clonar o repositório

```bash
git clone https://github.com/SEU_USUARIO/multi-agent-platform.git
cd multi-agent-platform
```

### 2. Subir o Kafka

```bash
docker compose up -d kafka
```

### 3. Backend

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn api.app:app --port 8000
```

Aguarde o log: `[api] Plataforma pronta. API no ar.`

### 4. Frontend (em outro terminal)

```bash
cd frontend
npm install
npm run dev
```

Acesse **http://localhost:5173**

---

## Como usar

### Interface web

- **Selecionar especialista:** use o dropdown no topo do chat para escolher entre modo automático ou um agente específico.
- **Conversar:** digite e envie; a resposta exibe o agente que respondeu, número de tokens e latência.
- **Customizar personalidade:** clique no botão ⚙️ para abrir o editor e ajustar nome, emoji, system prompt e temperatura. As mudanças persistem no navegador.

### CLI

```bash
python cli.py
```

---

## API REST

A documentação interativa (Swagger) fica disponível em **http://localhost:8000/docs**.

| Método | Endpoint        | Descrição                                  |
|--------|-----------------|--------------------------------------------|
| GET    | `/api/health`   | Status da API e número de agentes          |
| GET    | `/api/agents`   | Lista agentes, personas e capabilities     |
| GET    | `/api/stats`    | Estatísticas do orquestrador               |
| POST   | `/api/chat`     | Envia mensagens e recebe a resposta do LLM |

- `capability`: `"chat"` para round-robin, ou o id do agente para roteamento direto.
- `system` (opcional): sobrescreve a personalidade padrão do agente.

---

## Personas

As personalidades são definidas em `core/personas.py`. Cada persona vira um agente com uma capability dedicada (= seu id), além da capability compartilhada `chat`.

| Persona        | Especialidade                          | Criatividade |
|----------------|----------------------------------------|-------------|
| 🔬 Pesquisador | Respostas detalhadas e factuais        | 0.3         |
| 💻 Programador | Soluções técnicas e código limpo       | 0.2         |
| ✍️ Criativo    | Brainstorm e ideias fora da caixa      | 0.9         |

**Criar uma nova persona** — adicione uma entrada à lista `PERSONAS`:

```python
Persona(
    id="translator",
    name="Tradutor",
    emoji="🌐",
    description="Traduções precisas entre idiomas.",
    temperature=0.3,
    system="Você é um tradutor profissional. Traduza com precisão e naturalidade.",
)
```

Reinicie o backend e o novo agente aparecerá automaticamente na interface.

---
