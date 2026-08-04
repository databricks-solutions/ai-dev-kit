# Local Track — What Local Mode Does *Not* Cover

> Grounded against `omnigent 0.5.0.dev0`.

[Local Part 1](01-running-locally.md) covers what running locally buys you. This
page is the other half: the ceiling. Local mode is bounded by one fact — **a
local server is only reachable on your own network, and only while your laptop
is on.** Everything below follows from that. When one of these limits starts to
bite, that's your signal to graduate to the [Databricks track](../databricks/02-which-mode.md).

---

## The caveats

- **No off-network access / no "from anywhere."** Teammates not on your LAN, or
  you from a coffee shop, cannot reach `localhost:6767`. Sessions "follow you"
  only across devices on the same network. For true anywhere-access you either
  deploy a server (Docker/Render/Railway/Fly/Modal/Cloudflare/Databricks
  Apps, per `deploy/README.md`) or expose your laptop with a **Cloudflare quick
  tunnel** (public) or **Tailscale** (private).

- **No always-on availability.** Close the laptop and sessions stop. There's no
  server that keeps running or that can provision a **managed host** (a cloud
  sandbox per session) so work continues without your machine online.

- **Team collaboration is limited to your network.** Multi-user accounts *do*
  work locally (`OMNIGENT_AUTH_ENABLED=1 omnigent server start`, then
  **Admin → Members → Invite**), and live-session sharing, co-drive
  (`omnigent attach <id>`), and forking (`omnigent run --fork <id>`) all
  function — **but only for people who can reach the server.** For anyone off
  your network you need a deployed, always-on host.

- **No SSO out of the box.** OIDC login with Google/GitHub/Okta/Microsoft
  (`OMNIGENT_OIDC_ISSUER` + client ID/secret) and the proxy-only `header` auth
  mode are configured on a *deployed* server, not a casual local run.

- **SQLite, not a production database.** The local default is a machine-global
  SQLite file. Fine for one person; the deploy targets back onto Postgres
  (e.g. Lakebase on Databricks Apps) for concurrency and durability.

- **Cloud sandboxes are opt-in and need extras/credentials.** Running sessions
  in disposable Modal / Daytona / Islo / E2B / CoreWeave / Kubernetes /
  OpenShell / Boxlite sandboxes requires the matching extra
  (`pip install 'omnigent[modal]'`, etc.) and provider credentials — and Modal
  sandboxes are capped at 24h. This is beyond the plain local setup.

- **Platform gaps to know about:**
  - **Linux:** the native tmux/PTY terminal wrappers and the `pi` harness
    *require* `bwrap` (bubblewrap) and `tmux`; a missing `bwrap` makes those
    terminals fail to start. `Node.js 22+`/`npm` is needed for the
    npm-installed harnesses (Claude, Codex, OpenCode, Pi).
  - **Windows (native):** runs in a **degraded mode**. `omnigent server`, the
    web UI, and the **SDK-based** harnesses (claude-sdk / cursor / codex via
    `omnigent run <agent.yaml>`) work; the native tmux/PTY terminal wrappers
    and `bwrap`/`seatbelt` filesystem+network sandboxing do **not**. Use
    Linux/macOS or WSL for the full experience.

---

## Quick decision guide

| You want… | Local is enough? |
|---|---|
| Try the meta-harness, author agents, private single-user work | ✅ Yes |
| Same session across your own laptop + phone on home Wi-Fi | ✅ Yes |
| OS sandboxing + policies + spend caps | ✅ Yes (Linux/macOS) |
| Access from anywhere / when laptop is off | ❌ Deploy a server (or tunnel) |
| Teammates off your network | ❌ Deploy an always-on host |
| SSO, Postgres durability, per-session cloud sandboxes | ❌ Deploy (see `deploy/README.md`) |

When you hit a ❌, head to the [Databricks track](../databricks/02-which-mode.md)
to pick your next step.
