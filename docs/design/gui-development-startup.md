# Authenticated GUI development startup (Prompt 15)

Use this worktree and its existing virtual environment. Leave the running port-5001
service untouched. This creates a separate development application on loopback
port 5002 with isolated settings, files index, logs and other relative stores.
No paid provider request is required. Do not point this procedure at an existing
operational database or import a production backup.

```bash
cd /home/patch/Projects/scidk-knowledge-curation
env -i PATH=/usr/bin:/bin PYTHONPATH=/home/patch/Projects/scidk-knowledge-curation \
  /home/patch/PycharmProjects/scidk/.venv/bin/python -m scidk.dev_gui \
  --state-dir /tmp/scidk-prompt15-dev --init-admin dev-admin \
  --configure scidk.dev_system_demo:configure --port 5002
```

Enter a new matching password (at least 12 characters) at the terminal prompts.
Then visit `http://127.0.0.1:5002/login` and sign in as `dev-admin`. On later
launches omit `--init-admin`; it refuses an existing user store. Keep the same
state directory. `/tmp` state is disposable; for persistence choose a dedicated
private development directory. Never commit its databases, keys or logs.

The launcher sets actual Python `True` flags for GUI v3, readiness, Knowledge
context, curation, sharing, Overview and Review chat/workspace. It disables
scheduler startup and concept-graph connections, chooses the memory graph, and
refuses inherited graph connection settings. It disables dotenv discovery before
importing the production factory. Use a clean process as above; it deliberately
changes cwd and process environment and is not an embedded production factory.
Production defaults remain unchanged. No running server is stopped or restarted.

The optional trusted local `module:function` hook assembles services. The supplied
`scidk.dev_system_demo:configure` hook requires exactly one enabled named admin and
adds one explicitly synthetic System projection with a source Resource and pinned
fixture/hash/git provenance. It grants only this admin the synthetic Resource,
Context metadata and fixed Overview System tool. It creates no research assertions,
human decisions, accepted facts, ReviewService or Neo4j writes. Review flags alone
do not create a review backend: Review remains unavailable until a separately
configured, ontology-compatible ledger/review service is supplied. Omitting the
hook leaves Knowledge services unavailable, accurately shown in readiness.

## Local fake-provider demonstration

In a second terminal start the deterministic provider; it binds loopback and
never forwards requests, logs prompts or uses Parley:

```bash
cd /home/patch/Projects/scidk-knowledge-curation
env -i PATH=/usr/bin:/bin PYTHONPATH=/home/patch/Projects/scidk-knowledge-curation \
  /home/patch/PycharmProjects/scidk/.venv/bin/python -m scidk.dev_system_demo --port 5010
```

While signed in, use Settings → AI Chat → LLM Provider: Custom endpoint,
`http://127.0.0.1:5010/v1`, model `synthetic-demo`, no key. Save personal settings.
Model listing or connection testing verifies transport only; it does not approve
a destination. As the trusted local operator, explicitly approve only that exact
local synthetic destination in a third terminal:

```bash
cd /home/patch/Projects/scidk-knowledge-curation
env -i PATH=/usr/bin:/bin PYTHONPATH=/home/patch/Projects/scidk-knowledge-curation \
  /home/patch/PycharmProjects/scidk/.venv/bin/python - <<'PY'
from scidk.core.auth import AuthManager
from scidk.agent_tools.security import PolicyStore
state_db = '/tmp/scidk-prompt15-dev/scidk_settings.db'
auth = AuthManager(state_db)
try:
    users = auth.list_users(include_disabled=True)
    assert len(users) == 1 and users[0]['role'] == 'admin' and users[0]['enabled']
    PolicyStore(state_db).approve_destination(
        'prompt15-local-fake', 'http://127.0.0.1:5010/v1', 'synthetic-demo',
        'low', admin_id=users[0]['id'])
finally:
    auth.close()
PY
```

Open `/admin/chat-readiness`: select Overview/System context and enter
`system:synthetic-demo`. The checks distinguish configuration, exact model approval,
service readiness, tool grant, Resource availability and context authorization.
Connectivity is always labeled unverified by this no-network diagnostic; a
successful connection test or chat is separate evidence. A key is optional for
the local fake, so `credential_present=false` is informational.

At `/overview`, select System context, enter the same stable ID, ask a synthetic
question and explicitly check the disclosure consent box. The response is a
constant synthetic explanation. No history, model-selected tools or arbitrary
query is sent. A remote provider requires a separately approved exact destination,
credential/usage rights and explicit authorization for paid calls/content.

## First-administrator bootstrap and configured operation

First-run setup is preserved through existing AuthManager user creation (the CLI
above prompts locally). A fresh server never treats anonymous callers as admins.
Embedders retaining HTTP setup at `POST /api/settings/security/auth` must explicitly
configure a random, private `SCIDK_AUTH_BOOTSTRAP_TOKEN` of at least 32 characters
in Flask config and supply it in `X-SciDK-Bootstrap`. This is loopback-only,
same-origin, without Authorization headers, only for enabling first-user auth
when there are no users or legacy password. First creation is serialized. Never
place the token in URLs, templates, logs or public configuration. This is an
operator integration, not a token shipped in the GUI. Local CLI setup is preferred.

After first-user creation, that token confers no access; auth mutation, global
credential registry/testing and configuration import/export/backup require an
unlocked named-admin cookie session. API tokens, header sessions, ordinary users,
legacy/no-auth sessions and cross-origin callers are refused for these global
operations. Personal provider settings remain available to named users (including
named header sessions); environment import retains its stricter single-user,
named-admin cookie boundary. Existing legacy single-user installations need a
trusted local named-admin provisioning step; no anonymous elevation is added.
