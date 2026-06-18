# Firebase — Auth e Storage (projetos separados)

O Econmesh usa **dois projetos Firebase** distintos:

| Projeto | Responsabilidade | Onde configura |
| ------- | ---------------- | -------------- |
| **Auth** | Login, registro, verificação de ID token, custom claims (`role`) | API + apps web (Next.js) |
| **Storage** | Upload de imagens (oportunidades, logos, avatares) | API (presigned URLs) |

O frontend **não** envia arquivos diretamente ao Firebase Client SDK. O fluxo é:

1. App chama a API (`POST .../presign`) com o token de auth.
2. API gera URL assinada no projeto **Storage**.
3. App faz `PUT` do arquivo nessa URL.
4. A URL pública (`firebasestorage.googleapis.com`) é salva no MongoDB.

---

## 1. Projeto Firebase Auth

### Console Firebase → Auth

1. Ative **Authentication** → provedor **E-mail/senha**.
2. (Opcional) Domínios autorizados para o app web.

### Service account (API)

1. **Configurações do projeto** → **Contas de serviço**.
2. **Gerar nova chave privada** → salve o JSON (nunca commite).
3. A conta precisa de permissão para **Firebase Authentication Admin** (padrão da service account do Admin SDK).

### Web app (frontend `econmesh-app` e `econmesh-admin`)

1. **Configurações do projeto** → **Seus apps** → adicione app **Web**.
2. Copie os valores do `firebaseConfig` para o `.env`:

```env
# econmesh-app / econmesh-admin — projeto AUTH
NEXT_PUBLIC_FIREBASE_API_KEY=
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=          # ex: meu-auth.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=           # ex: meu-auth
NEXT_PUBLIC_FIREBASE_APP_ID=
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=
```

### Variáveis da API (Auth)

```env
FIREBASE_CREDENTIALS_SOURCE=path           # ou json em produção
FIREBASE_CREDENTIALS_PATH=./secrets/firebase-auth.json
FIREBASE_PROJECT_ID=meu-auth
```

Em Dokploy/Render (sem arquivo no disco):

```env
FIREBASE_CREDENTIALS_SOURCE=json
FIREBASE_CREDENTIALS_JSON={"type":"service_account",...}
FIREBASE_PROJECT_ID=meu-auth
```

---

## 2. Projeto Firebase Storage

### Console Firebase → Storage

1. Crie o bucket (**Storage** → **Começar**).
2. Anote o nome do bucket (ex: `meu-storage.appspot.com` ou `meu-storage.firebasestorage.app`).
3. Configure regras de acesso conforme sua política (uploads vão por URL assinada gerada pela API com service account).

### Service account (API)

1. No projeto **Storage**, gere outra chave de **conta de serviço** (pode ser a padrão `firebase-adminsdk-...`).
2. A conta precisa de permissão para **Cloud Storage** no bucket (a service account do Firebase Admin SDK já inclui isso no mesmo projeto).

### Variáveis da API (Storage)

Quando auth e storage são **projetos diferentes** (recomendado):

```env
FIREBASE_STORAGE_CREDENTIALS_SOURCE=path
FIREBASE_STORAGE_CREDENTIALS_PATH=./secrets/firebase-storage.json
FIREBASE_STORAGE_PROJECT_ID=meu-storage
FIREBASE_STORAGE_BUCKET=meu-storage.appspot.com
```

Em produção com JSON inline:

```env
FIREBASE_STORAGE_CREDENTIALS_SOURCE=json
FIREBASE_STORAGE_CREDENTIALS_JSON={"type":"service_account",...}
FIREBASE_STORAGE_PROJECT_ID=meu-storage
FIREBASE_STORAGE_BUCKET=meu-storage.appspot.com
```

### Mesmo projeto para tudo (setup simples)

Se auth e storage estiverem no **mesmo** projeto Firebase, basta definir o bucket — a API reutiliza as credenciais de auth:

```env
FIREBASE_CREDENTIALS_PATH=./secrets/firebase.json
FIREBASE_PROJECT_ID=meu-projeto
FIREBASE_STORAGE_BUCKET=meu-projeto.appspot.com
# FIREBASE_STORAGE_CREDENTIALS_* não é necessário
```

---

## 3. Estrutura local de secrets (Docker / dev)

```
econmesh-api/
└── secrets/
    ├── firebase-auth.json      # service account do projeto Auth
    └── firebase-storage.json   # service account do projeto Storage
```

O `docker-compose.yml` monta `./secrets` em `/app/secrets:ro`.

Adicione `secrets/` ao `.gitignore` (já ignorado se contiver `*.json` sensível).

---

## 4. Endpoints que usam Storage

| Recurso | Endpoint presign |
| ------- | ---------------- |
| Avatar do usuário | `POST /api/v1/users/avatar/presign` |
| Logo da empresa | `POST /api/v1/companies/logo/presign` |
| Imagens de oportunidade | `POST /api/v1/opportunities/images/presign` |

Chaves no bucket seguem o padrão (pasta raiz ``econmesh/``):

- `econmesh/avatars/{user_id}/{uuid}.{ext}`
- `econmesh/logos/{user_id}/{uuid}.{ext}`
- `econmesh/images/{user_id}/{uuid}.{ext}`

---

## 5. Checklist de deploy

- [ ] Projeto Auth: Authentication ativo, web app registrado, service account na API
- [ ] Projeto Storage: bucket criado, service account na API com acesso ao bucket
- [ ] `FIREBASE_PROJECT_ID` = ID do projeto **Auth**
- [ ] `FIREBASE_STORAGE_BUCKET` = bucket do projeto **Storage**
- [ ] Credenciais de storage separadas se os projetos forem diferentes
- [ ] Frontends (`econmesh-app`, `econmesh-admin`) usam apenas variáveis `NEXT_PUBLIC_FIREBASE_*` do projeto **Auth**
- [ ] CORS da API inclui origens dos frontends

---

## 6. Solução de problemas

| Sintoma | Causa provável |
| ------- | -------------- |
| `ID token is invalid` | `FIREBASE_PROJECT_ID` não corresponde ao projeto que emitiu o token (frontend apontando para outro projeto) |
| `Firebase Storage is not configured` | `FIREBASE_STORAGE_BUCKET` ausente |
| `Unable to generate upload URL` | Credenciais de storage incorretas ou service account sem permissão no bucket |
| Upload PUT retorna 403 | Bucket/regras do Storage ou `Content-Type` diferente do presign |
| Imagem não carrega no browser | URL pública bloqueada por regras do Storage; ajuste regras ou use token de download |
