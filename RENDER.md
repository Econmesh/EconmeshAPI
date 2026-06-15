# Deploy da Econmesh API no Render

Guia para publicar a API FastAPI no [Render](https://render.com) usando o runtime **Python 3** (Poetry).

## Pré-requisitos

| Recurso | Onde provisionar |
| --- | --- |
| **MongoDB** | [MongoDB Atlas](https://www.mongodb.com/atlas) (recomendado) |
| **Redis** | [Render Key Value](https://render.com/docs/redis) ou [Upstash](https://upstash.com) |
| **Firebase** | Console Firebase — service account JSON |
| **Repositório Git** | GitHub / GitLab / Bitbucket conectado ao Render |

Arquivos deste repositório usados no deploy:

| Arquivo | Função |
| --- | --- |
| `pyproject.toml` + `poetry.lock` | Dependências (Poetry) |
| `.python-version` | Python `3.14.3` no Render |
| `build.sh` | Instala dependências de produção |
| `start.sh` | Sobe gunicorn + uvicorn na porta `$PORT` |
| `render.yaml` | Blueprint opcional (IaC) |

---

## Opção A — Blueprint (`render.yaml`)

1. No Render: **New → Blueprint**.
2. Conecte este repositório e confirme o `render.yaml`.
3. Após o primeiro deploy, abra **Environment** e preencha as variáveis marcadas como secretas (veja tabela abaixo).
4. Faça **Manual Deploy** para aplicar os secrets.

---

## Opção B — Web Service manual

### 1. Criar o serviço

1. **New → Web Service** → selecione o repositório.
2. Configure:

| Campo | Valor |
| --- | --- |
| **Language** | `Python 3` |
| **Branch** | `main` (ou a branch desejada) |
| **Build Command** | `./build.sh` |
| **Start Command** | `./start.sh` |
| **Health Check Path** | `/health` |

### 2. Build Command (referência)

```bash
./build.sh
```

Equivalente interno:

```bash
poetry install --only main --no-root --no-ansi
```

### 3. Start Command (referência)

```bash
./start.sh
```

Equivalente interno:

```bash
poetry run gunicorn src.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w 2 \
  -b 0.0.0.0:$PORT \
  --access-logfile - \
  --error-logfile - \
  --timeout 60
```

> O Render injeta a variável `PORT` automaticamente. Não fixe a porta `8000` no start command.

### 4. Versões de runtime

| Variável | Valor recomendado |
| --- | --- |
| `PYTHON_VERSION` | `3.14.3` |
| `POETRY_VERSION` | `2.1.3` |

Alternativa: o arquivo `.python-version` na raiz já define `3.14.3`.

---

## Variáveis de ambiente

### Obrigatórias em produção

| Variável | Exemplo / notas |
| --- | --- |
| `ENV` | `production` |
| `MONGO_URI` | `mongodb+srv://user:pass@cluster.mongodb.net` |
| `MONGO_DB` | `econmesh` |
| `REDIS_URL` | `rediss://default:pass@host:6379` (TLS se o provedor exigir) |
| `FIREBASE_CREDENTIALS_JSON` | JSON completo da service account (uma linha) |
| `FIREBASE_PROJECT_ID` | ID do projeto Firebase |
| `FIREBASE_STORAGE_BUCKET` | `seu-projeto.appspot.com` |

> Use `FIREBASE_CREDENTIALS_JSON` no Render em vez de arquivo (`FIREBASE_CREDENTIALS_PATH`). Cole o conteúdo do `serviceAccountKey.json` como secret.

### Recomendadas

| Variável | Valor sugerido |
| --- | --- |
| `LOG_JSON` | `true` |
| `ENABLE_DOCS` | `false` (desliga `/docs` em produção) |
| `WEB_CONCURRENCY` | `2` (ajuste conforme o plano; free tier: `1`–`2`) |
| `CORS_ORIGINS` | `["https://app.econmesh.com"]` |
| `TRUSTED_HOSTS` | `["econmesh-api.onrender.com"]` |
| `FRONTEND_VERIFY_URL` | URL do frontend para verificação de e-mail |

### E-mail (opcional)

| Variável | Quando usar |
| --- | --- |
| `MAIL_ENABLED` | `true` para enviar e-mails |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` | Credenciais do provedor SMTP |

Lista completa: `.env.example`.

---

## Dependências externas

### MongoDB Atlas

1. Crie um cluster e um usuário com senha.
2. Em **Network Access**, libere `0.0.0.0/0` (ou os IPs do Render, se preferir restringir).
3. Copie a connection string e defina `MONGO_URI`.

### Redis

- **Render Key Value**: crie o recurso e use a **Internal URL** em `REDIS_URL` (mesma região do web service).
- **Upstash**: use a URL `rediss://` fornecida.

### Índices MongoDB (pós-deploy)

Após o primeiro deploy bem-sucedido, rode uma vez (Render Shell ou job local apontando para Atlas):

```bash
poetry run python -m src.scripts.create_indexes
```

---

## Health checks

| Endpoint | Uso |
| --- | --- |
| `GET /health` | Liveness — configure no Render como **Health Check Path** |
| `GET /health/ready` | Readiness — valida MongoDB + Redis |

---

## Opção C — Docker no Render

Se preferir o `Dockerfile` em vez do runtime Python nativo:

| Campo | Valor |
| --- | --- |
| **Language** | `Docker` |
| **Dockerfile Path** | `./Dockerfile` |

O `Dockerfile` usa `docker-entrypoint.sh`, que escuta em `0.0.0.0:$PORT` (padrão `8000`). Defina `PORT=8000` no painel se necessário.

Build local (teste):

```bash
docker build -t econmesh-api .
docker run --rm -p 8000:8000 --env-file .env econmesh-api
```

---

## Troubleshooting

| Sintoma | Causa provável | Solução |
| --- | --- | --- |
| `bash: poetry: command not found` | Runtime errado | Use **Python 3**, não Node/Docker (na opção nativa) |
| `Current Python version … is not allowed` | Versão incompatível | Defina `PYTHON_VERSION=3.14.3` |
| App não responde / timeout | Porta fixa | Use `./start.sh` (liga em `$PORT`) |
| Crash no boot: Firebase | Credenciais ausentes | Defina `FIREBASE_CREDENTIALS_JSON` |
| `/health/ready` degraded | Mongo/Redis inacessível | Verifique `MONGO_URI`, `REDIS_URL` e firewall |
| Build lento | Lock ausente | Commit `poetry.lock` (já versionado) |

Logs: **Dashboard → seu serviço → Logs**.

---

## Checklist de deploy

- [ ] `poetry.lock` commitado no repositório
- [ ] Web Service com `build.sh` e `start.sh`
- [ ] `PYTHON_VERSION=3.14.3`
- [ ] `MONGO_URI` e `REDIS_URL` configurados
- [ ] `FIREBASE_CREDENTIALS_JSON` como secret
- [ ] `ENV=production`, `LOG_JSON=true`, `ENABLE_DOCS=false`
- [ ] `CORS_ORIGINS` e `TRUSTED_HOSTS` do domínio real
- [ ] Health check em `/health`
- [ ] Índices Mongo criados (`create_indexes`)
- [ ] `GET /health/ready` retorna `ok`
