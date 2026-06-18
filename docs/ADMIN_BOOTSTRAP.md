# Bootstrap do primeiro administrador

Este guia descreve como criar manualmente o **primeiro usuário admin** para acessar o painel `econmesh-admin`.

## Pré-requisitos

- Projeto Firebase configurado (mesmo usado pela API)
- MongoDB acessível (mesma instância da API)
- API rodando com variáveis de ambiente corretas

## Passo 1 — Criar usuário no Firebase

1. Acesse o [Firebase Console](https://console.firebase.google.com/)
2. Selecione o projeto da Econmesh
3. Vá em **Authentication** → **Users** → **Add user**
4. Informe e-mail e senha do administrador
5. Anote o **UID** do usuário criado

## Passo 2 — Definir custom claim `role=admin`

O RBAC da API lê a role do token Firebase. Defina a claim via Firebase Admin SDK ou script:

```python
import firebase_admin
from firebase_admin import auth, credentials

cred = credentials.Certificate("path/to/serviceAccountKey.json")
firebase_admin.initialize_app(cred)

auth.set_custom_user_claims("FIREBASE_UID_AQUI", {"role": "admin"})
```

Substitua `FIREBASE_UID_AQUI` pelo UID anotado no passo 1.

> Após alterar claims, o usuário precisa fazer **logout e login** novamente para obter um ID token atualizado.

## Passo 3 — Inserir registro no MongoDB

Na collection `users`, insira um documento espelhando o usuário Firebase:

```json
{
  "_id": "<UUID gerado>",
  "firebase_uid": "FIREBASE_UID_AQUI",
  "email": "admin@exemplo.com",
  "name": "Admin Econmesh",
  "email_verified": true,
  "is_verified": true,
  "is_active": true,
  "role": "admin",
  "created_at": { "$date": "2026-01-01T00:00:00.000Z" },
  "updated_at": { "$date": "2026-01-01T00:00:00.000Z" }
}
```

Campos obrigatórios para login:

| Campo | Valor |
|-------|-------|
| `firebase_uid` | UID do Firebase |
| `role` | `"admin"` |
| `is_verified` | `true` |
| `is_active` | `true` |

## Passo 4 — Acessar o painel admin

1. Inicie a API: `poetry run uvicorn src.main:app --reload`
2. Inicie o admin: `npm run dev:web` (porta 3002)
3. Acesse `http://localhost:3002/login`
4. Faça login com o e-mail e senha criados

O frontend chama `POST /api/v1/auth/admin/login`, que rejeita usuários sem `role=admin`.

## Criar outros admins e usuários

Após o primeiro admin estar ativo:

- **Novos admins**: painel admin → Usuários → Novo usuário → role `admin`
- **Usuários normais**: mesmo fluxo com role `viewer`, `operator` ou `analyst`
- **API**: `POST /api/v1/admin/users` (requer token de admin)

Somente admins autenticados podem criar outros admins. Não há autocadastro no painel admin.

## Troubleshooting

| Problema | Solução |
|----------|---------|
| `403 admin_required` no login | Verifique custom claim `role=admin` e faça logout/login no Firebase |
| `403 account_not_verified` | Defina `is_verified: true` no Mongo |
| `403 account_disabled` | Defina `is_active: true` no Mongo e habilite o usuário no Firebase |
| Token sem role atualizada | Revogue sessões ou aguarde refresh; claims só entram em novo ID token |
