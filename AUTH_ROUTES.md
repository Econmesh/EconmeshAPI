# Auth no econmesh-api

## Status atual (cadastro/login)

- **Login**: implementado e funcional. Agora **bloqueia** o acesso ate a conta ser confirmada (`is_verified`) e exige conta ativa (`is_active`).
- **Cadastro**: implementado em `POST /api/v1/auth/register` (usuario padrao) e `POST /api/v1/auth/admin/users` (criacao privilegiada, somente admin).
- **Validacao de conta**: implementada via token de uso unico com expiracao (24h) em `POST /api/v1/auth/verify` (reenvio em `POST /api/v1/auth/resend-verification`).
- **Fonte de identidade**: o Firebase continua sendo o store de credenciais (email/senha). O cadastro cria a identidade no Firebase (via Admin SDK) e espelha o usuario no MongoDB; o `role` e gravado como custom claim.
- **Teste**: `poetry run pytest src/tests/modules/auth/` -> `16 passed`.

## Tipos de usuario / papeis

- Papel padrao do auto-cadastro: `DEFAULT_ROLE` (`viewer`) — o "usuario padrao".
- `admin`: criado **somente** por um admin autenticado, via `POST /api/v1/auth/admin/users` (protegido por `require_role(Role.ADMIN)`).
- O papel e persistido no MongoDB e como custom claim `role` no Firebase.

## Fluxo de cadastro + confirmacao

1. Cliente chama `POST /api/v1/auth/register` com nome, email, telefone (opc), senha (e confirmacao opcional).
2. A API cria a identidade no Firebase (email/senha, `email_verified=false`), define o claim `role=viewer`, e cria o documento em `users` com `is_verified=false`.
3. Um token de confirmacao (hash SHA-256 + expiracao) e gravado em `email_verifications`. Fora de producao, o token bruto e retornado na resposta (`verification_token`) para permitir o fluxo sem SMTP. **TODO**: disparar e-mail real quando o provedor de e-mail for integrado.
4. Usuario confirma em `POST /api/v1/auth/verify` (corpo `{ "token": "<raw>" }`): marca `is_verified=true`/`email_verified=true` e seta `email_verified=true` no Firebase.
5. So entao o `POST /api/v1/auth/login` (com `id_token` do Firebase) passa pelo gate de verificacao.

Criacao por admin (`POST /api/v1/auth/admin/users`) aceita `role` e `auto_confirm` (default `true`), criando a conta ja confirmada.

## Base de URL

- Prefixo global da API: `/api/v1`
- Prefixo do modulo auth: `/auth`
- Rotas finais:
  - `POST /api/v1/auth/register`
  - `POST /api/v1/auth/admin/users` (somente admin)
  - `POST /api/v1/auth/verify`
  - `POST /api/v1/auth/resend-verification`
  - `POST /api/v1/auth/login`
  - `GET /api/v1/auth/me`
  - `POST /api/v1/auth/logout`
  - `POST /api/v1/auth/revoke-all`

## Como o Firebase Auth entra no fluxo

1. O app inicializa o Firebase Admin no startup (`firebase.init()`), usando `FIREBASE_CREDENTIALS_SOURCE`:
   - `path` → `FIREBASE_CREDENTIALS_PATH` (arquivo JSON no disco)
   - `json` → `FIREBASE_CREDENTIALS_JSON` (JSON inline em variável de ambiente)
2. O cliente autentica no Firebase (frontend/mobile) e envia o **Firebase ID token** para a API.
3. A API valida o token via `firebase.verify_id_token(...)`.
4. Claims decodificados sao usados para:
   - sincronizar usuario em Mongo (`users`);
   - montar sessao em Redis;
   - extrair papel (`role`) por custom claim.
5. Em rotas protegidas, o Bearer token e lido no header `Authorization: Bearer <token>` e validado novamente.

## Rotas e atributos relacionados

### 1) `POST /api/v1/auth/login`

Finalidade:
- Verificar `id_token` do Firebase.
- Criar/atualizar usuario local.
- Retornar identidade e introspeccao basica do token.

Body (`LoginRequest`):
- `id_token` (string, obrigatorio, min_length=20)

Resposta 200 (`LoginResponse`):
- `user` (`MeResponse`)
  - `id` (UUID)
  - `firebase_uid` (string)
  - `email` (Email | null)
  - `name` (string | null)
  - `picture` (string | null)
  - `email_verified` (bool)
  - `role` (enum `Role`)
  - `is_active` (bool)
  - `created_at` (datetime)
  - `updated_at` (datetime)
  - `last_login_at` (datetime | null)
- `token` (`TokenIntrospectionResponse`)
  - `uid` (string)
  - `issuer` (string | null)
  - `audience` (string | null)
  - `expires_at` (int epoch | null)
  - `issued_at` (int epoch | null)
  - `email_verified` (bool)

Efeitos colaterais:
- MongoDB (`users`):
  - upsert por `firebase_uid`
  - atualiza `email`, `name`, `picture`, `email_verified`, `last_login_at`, `updated_at`
  - cria no insert: `_id`, `firebase_uid`, `created_at`, `is_active=true`
  - persiste claims extras em `custom_claims`
- Redis:
  - grava hash de sessao em `auth:session:{uid}`
  - TTL da sessao: `SESSION_TTL_SECONDS`
- Limpa `auth:revoked:{uid}` no Redis ao concluir login com token valido.

### 2) `GET /api/v1/auth/me`

Finalidade:
- Retornar usuario autenticado atual.

Autenticacao:
- Requer `Authorization: Bearer <firebase_id_token>`.

Resposta 200 (`MeResponse`):
- mesmos campos de `user` acima.

Erros comuns:
- 401 `missing_token` quando header nao e enviado.
- 404 `user_not_found` se token valido, mas usuario nao existe na base local.

### 3) `POST /api/v1/auth/logout`

Finalidade:
- Invalidar sessao local atual.

Autenticacao:
- Requer Bearer token valido.

Resposta 200 (`MessageResponse`):
- `message`: `"Signed out successfully."`

Efeitos:
- remove `auth:session:{uid}` do Redis.

### 4) `POST /api/v1/auth/revoke-all`

Finalidade:
- Logout global ("logout everywhere").

Autenticacao:
- Requer Bearer token valido.

Resposta 200 (`MessageResponse`):
- `message`: `"All sessions were revoked."`

Efeitos:
- chama Firebase Admin: `revoke_refresh_tokens(uid)`.
- aplica o mesmo fluxo de `logout` local no Redis.

## Claims/atributos usados do Firebase

Principais claims lidos:
- `uid`
- `email`
- `name`
- `picture`
- `email_verified`
- `iss`
- `aud`
- `exp`
- `iat`
- `role` (custom claim opcional)

Mapeamento de role:
- Se `role` vier como string valida, vira `Role(...)`.
- Se ausente/invalida, cai em `DEFAULT_ROLE`.

## Conclusao objetiva

- **Ja esta funcionando?** Sim, o fluxo de autenticacao (register/verify/login/me/logout/revoke-all) esta implementado e com testes passando.
- **Existe cadastro separado?** Sim. `POST /auth/register` (usuario padrao) e `POST /auth/admin/users` (admin). A confirmacao de conta e obrigatoria antes do login.
