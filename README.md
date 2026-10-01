# 📅 IdeaAgenda

Sistema inteligente de organização de tarefas com sincronização com o Google Agenda e sugestões automáticas usando IA.

---

## 🚀 Visão Geral

**IdeaAgenda** é um sistema de gerenciamento de tarefas que permite:
- Criar, editar, concluir e excluir tarefas (com prioridade, categoria, duração e horário)
- Sincronizar automaticamente as tarefas com o **Google Agenda** (ida e volta)
- Organizar a rotina com **IA** — o dono do sistema escolhe entre **OpenAI** e **Google Gemini**
- Criar tarefas em linguagem natural ("reunião com o time sexta às 15h")
- Visualizar a semana agrupada por *Atrasadas, Hoje, Amanhã, Próximos 7 dias…*
- Acompanhar os **logs** do sistema, armazenados no **Redis**

Front-end em Angular, back-end com FastAPI, PostgreSQL como banco e Redis para logs e rate limit. Tudo sobe com Docker Compose.

---

## 🧪 Funcionalidades

- [x] CRUD de Tarefas
- [x] Sincronização com Google Calendar (envio, importação, edição e exclusão nos dois sentidos)
- [x] Sugestões de organização com IA (OpenAI **ou** Gemini, escolhido pelo dono)
- [x] Criação de tarefas por linguagem natural com IA
- [x] Importação de eventos existentes da Google Agenda
- [x] Autenticação com OAuth2 (Google) + JWT
- [x] Painel do dono: troca de provedor/modelo de IA e visualização de logs
- [x] Logs estruturados no Redis (Redis Streams)
- [x] Aplicação dockerizada
- [ ] Integrações futuras com Notion e Trello

---

## 🛠️ Tecnologias Utilizadas

| Camada         | Tecnologia                                   |
|----------------|----------------------------------------------|
| Frontend       | Angular 19 (standalone components + signals) |
| Backend        | Python 3.12, FastAPI, SQLAlchemy (async)     |
| Banco de Dados | PostgreSQL 16                                |
| Logs / cache   | Redis 7 (Streams)                            |
| Integrações    | Google Calendar API, OpenAI, Google Gemini   |
| Autenticação   | OAuth 2.0 (Google) + JWT                     |
| Infra          | Docker, Docker Compose, Nginx                |

---

## ⚡ Como rodar (Docker)

```bash
cp .env.example .env        # preencha as chaves (veja abaixo)
docker compose up -d --build
```

Acesse **http://localhost:8080**. A documentação da API fica em **http://localhost:8080/docs**.

| Serviço    | O que faz                                                        |
|------------|------------------------------------------------------------------|
| `frontend` | Nginx servindo o Angular e fazendo proxy de `/api` para o backend |
| `backend`  | API FastAPI (porta interna 8000)                                  |
| `postgres` | Banco de dados (volume `postgres_data`)                           |
| `redis`    | Logs em Redis Streams + rate limit da IA (volume `redis_data`)     |

### Configuração mínima do `.env`

1. **`SECRET_KEY`** – gere uma chave: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
2. **Login com Google + Google Agenda**
   - No [Google Cloud Console](https://console.cloud.google.com/apis/credentials) crie um *OAuth Client ID* do tipo **Aplicativo da Web**.
   - Ative a **Google Calendar API** no projeto.
   - Em *URIs de redirecionamento autorizados* adicione `http://localhost:8080/api/auth/google/callback` (ou o domínio de produção).
   - Preencha `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e `GOOGLE_REDIRECT_URI`.
   - Enquanto o app estiver em modo de teste no Google, adicione seu e-mail como *usuário de teste* na tela de consentimento.
3. **IA** – preencha `OPENAI_API_KEY` e/ou `GEMINI_API_KEY`. `AI_PROVIDER` define o padrão inicial.
4. **Dono do sistema** – coloque seu e-mail em `ADMIN_EMAILS`. Se ficar vazio, o primeiro usuário a entrar vira o dono.

> Para testar sem Google, use `ALLOW_DEV_LOGIN=true` (login só com e-mail). **Nunca** deixe ativado em produção.

---

## 🤖 IA: OpenAI ou Gemini (escolha do dono)

O dono acessa **Painel do dono → Provedor de IA**, escolhe **OpenAI** ou **Google Gemini** e, opcionalmente, o modelo
(ex.: `gpt-4o-mini`, `gemini-2.5-flash`). A escolha é salva no banco e vale para todos os usuários na hora, sem reiniciar.
As chaves de API ficam apenas no `.env` do servidor — o painel mostra se cada uma está configurada.

Recursos de IA:
- **Organizar minha semana** (`POST /api/ai/suggestions`): propõe horários para as tarefas sem data ou atrasadas,
  respeitando o expediente e os compromissos já marcados. O usuário revisa e aplica as que quiser (`/api/ai/suggestions/apply`);
  as tarefas aplicadas vão para o Google Agenda automaticamente.
- **Adicionar com IA** (`POST /api/ai/parse`): transforma uma frase em tarefa preenchida para revisão.
- Limite de uso por usuário/hora (`AI_RATE_LIMIT_PER_HOUR`), controlado no Redis.

---

## 📅 Sincronização com Google Agenda

- Ao criar/editar/excluir uma tarefa **com data**, o evento correspondente é criado/atualizado/removido no Google.
- **Sincronizar agora** faz a sincronização completa: envia alterações pendentes e importa/atualiza/remove tarefas a partir
  dos eventos do Google (últimos 7 dias até os próximos 60).
- Tarefas concluídas aparecem com ✅ no título do evento; a cor do evento segue a prioridade.
- Os tokens do Google ficam criptografados no banco (Fernet derivado da `SECRET_KEY`).

---

## 📜 Logs no Redis

Todos os logs da API (requisições HTTP, logins, criação/edição de tarefas, sincronizações, chamadas de IA, erros) são
gravados em JSON no Redis Stream `ideaagenda:logs` (limitado a `LOG_MAX_ENTRIES`), além do stdout do container.

- Pelo app: **Painel do dono → Logs**, com filtro por nível e busca.
- Pela API: `GET /api/admin/logs?level=WARNING&q=sync&limit=100`.
- Direto no Redis:
  ```bash
  docker compose exec redis redis-cli XREVRANGE ideaagenda:logs + - COUNT 10
  ```

---

## 💻 Desenvolvimento local (sem Docker)

```bash
# Infra
docker compose up -d postgres redis

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example .env   # ajuste DATABASE_URL=postgresql+asyncpg://ideaagenda:ideaagenda@localhost:5432/ideaagenda
                          #        REDIS_URL=redis://localhost:6379/0 e FRONTEND_URL=http://localhost:4200
python main.py            # http://localhost:8000/docs

# Testes do backend (usam SQLite + fakeredis, sem serviços externos)
pytest

# Frontend
cd frontend/task-organization-system
npm install
npm start                 # http://localhost:4200 (proxy de /api para :8000)
```

> Para expor o Postgres/Redis no host durante o desenvolvimento, adicione `ports` aos serviços no `docker-compose.yml`
> ou use um `docker-compose.override.yml`.

---

## 📂 Estrutura do Projeto

```
ideaagenda/
├── backend/                     # FastAPI
│   ├── Config/                  # settings, banco, redis, logging (Redis Streams)
│   ├── Controller/              # rotas: auth, tasks, calendar, ai, admin, health
│   ├── Dto/                     # schemas Pydantic
│   ├── Mapper/                  # conversões modelo ⇄ DTO ⇄ evento do Google
│   ├── Middleware/              # log de requisições
│   ├── Model/                   # modelos SQLAlchemy
│   ├── Service/                 # regras de negócio, Google Calendar, IA (OpenAI/Gemini)
│   ├── tests/                   # pytest
│   └── Dockerfile
├── frontend/task-organization-system/   # Angular + Nginx (Dockerfile)
├── docs/                        # Documentação técnica
├── docker-compose.yml
└── .env.example
```

### Principais endpoints

| Método | Rota                          | Descrição                                   |
|--------|-------------------------------|---------------------------------------------|
| GET    | `/api/auth/google/login`      | Inicia o login com Google                   |
| GET    | `/api/auth/me`                | Usuário logado                              |
| GET    | `/api/tasks`                  | Lista tarefas (`status`, `start`, `end`, `q`) |
| POST   | `/api/tasks`                  | Cria tarefa                                 |
| PATCH  | `/api/tasks/{id}`             | Atualiza tarefa                             |
| DELETE | `/api/tasks/{id}`             | Exclui tarefa                               |
| POST   | `/api/calendar/sync`          | Sincronização completa com Google Agenda    |
| POST   | `/api/ai/suggestions`         | Sugestões de organização                    |
| POST   | `/api/ai/suggestions/apply`   | Aplica sugestões selecionadas               |
| POST   | `/api/ai/parse`               | Tarefa a partir de linguagem natural        |
| GET/PUT| `/api/admin/settings/ai`      | Provedor/modelo de IA (somente dono)        |
| GET    | `/api/admin/logs`             | Logs do Redis (somente dono)                |
| GET    | `/api/health`                 | Saúde do banco e do Redis                   |

---

## 👨‍💻 Desenvolvedores

| Nome           | GitHub                                      |
|----------------|---------------------------------------------|
| Luan Ferreira  | [@luanferreiradev](https://github.com/luanferreiradev) |
| João Gabriel   | [@joaochecchia](https://github.com/joaochecchia)       |

---

## 📄 Licença

Este projeto está licenciado sob a **Licença MIT** – veja o arquivo [LICENSE](LICENSE) para detalhes.
