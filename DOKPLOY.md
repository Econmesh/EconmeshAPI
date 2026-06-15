# Deploy da Econmesh API no Dokploy

Guia para publicar a API FastAPI no [Dokploy](https://dokploy.com) usando **Dockerfile**.

## Pré-requisitos

| Recurso | Onde provisionar |
| --- | --- |
| **MongoDB** | [MongoDB Atlas](https://www.mongodb.com/atlas) ou serviço Mongo no Dokploy |
| **Redis** | Instância Redis no Dokploy, Upstash ou servidor dedicado |
| **Firebase** | Console Firebase — service account JSON |
| **Repositório Git** | GitHub / GitLab / Bitbucket conectado ao Dokploy |
| **Servidor Dokploy** | VPS com Dokploy instalado (portas 80/443 abertas para SSL) |

Arquivos deste repositório usados no deploy:

| Arquivo | Função |
| --- | --- |
| `Dockerfile` | Build multi-stage da imagem de produção |
| `docker-entrypoint.sh` | Sobe gunicorn + uvicorn na porta `$PORT` |
| `.env.example` | Referência de todas as variáveis de ambiente |

---

## 1. Criar a aplicação no Dokploy

> **Docker Compose não é necessário** na Dokploy. Use **Build Type → Dockerfile**; o `docker-compose.yml` deste repositório serve apenas para subir a API localmente.

1. No painel Dokploy: **Create Project** → **Create Service** → **Application**.
2. Conecte o repositório Git (`econmesh-api`).
3. Em **Build Type**, selecione **Dockerfile**.
4. Configure:

| Campo | Valor |
| --- | --- |
| **Build Path** | `.` (raiz do repositório) |
| **Dockerfile Path** | `Dockerfile` |
| **Branch** | `main` (ou a branch desejada) |

5. Clique em **Deploy** para o primeiro build.

---

## 2. Porta e domínio

A API escuta na porta definida pela variável `PORT` (padrão **8000**).

1. Vá em **Domains** → **Add Domain**.
2. Informe o domínio (ex.: `api.econmesh.com`).
3. Defina **Container Port** como `8000`.
4. Ative **HTTPS** para certificado Let's Encrypt automático.

> O Traefik do Dokploy encaminha o tráfego externo (443) para a porta interna do container. Mantenha `PORT=8000` nas variáveis de ambiente, a menos que altere o entrypoint.

---

## 3. Health check

| Campo | Valor |
| --- | --- |
| **Path** | `/health` |
| **Port** | `8000` |

O endpoint `/health/ready` verifica MongoDB e Redis (readiness probe).

O `Dockerfile` inclui `HEALTHCHECK` interno; no Dokploy, configure o health check do serviço com o path acima.

---

## 4. Variáveis de ambiente

Em **Environment**, adicione as variáveis abaixo. O Dokploy injeta um arquivo `.env` em runtime.

### Obrigatórias (produção)

```bash
ENV=production
LOG_JSON=true
ENABLE_DOCS=false

MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net
MONGO_DB=econmesh

REDIS_URL=redis://:password@redis-host:6379/0

# Cole o JSON completo do service account (uma linha):
FIREBASE_CREDENTIALS_JSON={"type":"service_account",...}
FIREBASE_PROJECT_ID=seu-projeto-id
FIREBASE_STORAGE_BUCKET=seu-projeto-id.appspot.com
```

### Recomendadas

```bash
PORT=8000
WEB_CONCURRENCY=2
LOG_LEVEL=INFO

CORS_ORIGINS=["https://app.econmesh.com"]
TRUSTED_HOSTS=["api.econmesh.com"]

MAIL_ENABLED=true
SMTP_HOST=smtp.seu-provedor.com
SMTP_PORT=587
SMTP_USERNAME=...
SMTP_PASSWORD=...
MAIL_FROM=no-reply@econmesh.com
FRONTEND_VERIFY_URL=https://app.econmesh.com/verify
```

### Firebase — duas opções

| Opção | Variável | Quando usar |
| --- | --- | --- |
| **JSON inline** (recomendado) | `FIREBASE_CREDENTIALS_JSON` | Dokploy / PaaS sem volume de secrets |
| Arquivo em disco | `FIREBASE_CREDENTIALS_PATH` | Se montar volume com o JSON |

Para Dokploy, prefira `FIREBASE_CREDENTIALS_JSON` com o conteúdo do `firebase-adminsdk-*.json` em uma única linha.

---

## 5. Serviços externos (MongoDB + Redis)

A API **não** sobe MongoDB nem Redis dentro do mesmo container. Provisione-os separadamente:

### Opção A — Serviços gerenciados (recomendado)

- **MongoDB Atlas** → use a connection string em `MONGO_URI`
- **Redis** (Upstash, Redis Cloud, etc.) → use a URL em `REDIS_URL`

### Opção B — Serviços no Dokploy

1. Crie um **Database** (MongoDB) ou **Compose** com Redis no mesmo projeto Dokploy.
2. Use o hostname interno do serviço na rede Docker do Dokploy (ex.: `econmesh-redis-production`).
3. Exemplo de `REDIS_URL`:

```bash
REDIS_URL=redis://econmesh-redis-production:6379/0
```

---

## 6. Build local (testar antes do deploy)

```bash
docker build -t econmesh-api:local .

docker run --rm -p 8000:8000 \
  -e ENV=development \
  -e MONGO_URI=mongodb://host.docker.internal:27017 \
  -e REDIS_URL=redis://host.docker.internal:6379/0 \
  -e FIREBASE_CREDENTIALS_JSON='{"type":"service_account",...}' \
  econmesh-api:local
```

Verifique:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/ready
```

---

## 7. Troubleshooting

### Container não inicia

- Confira os logs em **Deployments** → último deploy → **View Logs**.
- Verifique se `FIREBASE_CREDENTIALS_JSON` é JSON válido (sem quebras de linha).
- Confirme `MONGO_URI` e `REDIS_URL` acessíveis a partir do servidor Dokploy.

### 502 Bad Gateway no domínio

- A porta do domínio no Dokploy deve ser **8000** (ou o valor de `PORT`).
- O app deve escutar em `0.0.0.0`, não `127.0.0.1` (já configurado no entrypoint).

### CORS bloqueando o frontend

- Ajuste `CORS_ORIGINS` com a URL exata do frontend (incluindo `https://`).
- Formato: lista JSON, ex. `["https://app.econmesh.com"]`.

### TrustedHost rejeitando requests

- Se `TRUSTED_HOSTS` não for `["*"]`, inclua o domínio da API:
  `TRUSTED_HOSTS=["api.econmesh.com"]`

---

## Resumo rápido

```
Dokploy → Application → Dockerfile
  Build Path: .
  Dockerfile: Dockerfile
  Domain Port: 8000
  Health: /health
  ENV: production + MONGO_URI + REDIS_URL + FIREBASE_CREDENTIALS_JSON
```
