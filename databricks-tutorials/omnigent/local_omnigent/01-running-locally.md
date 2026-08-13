# Omnigent Tutorial — Part 1: Running Completely Locally

Omnigent is an open-source **meta-harness**: a single orchestration layer that
sits over Claude Code, Codex, Cursor, OpenCode, Hermes, Pi, and agents you
write yourself. The very first thing worth learning is how to run the whole
thing on one machine, with nothing deployed anywhere. That "fully local" mode
is the fastest way to understand the product, and it is genuinely useful on its
own — not just a demo.

This part covers two things:

1. How to bring Omnigent up locally, two ways.
2. What running locally actually buys you.

For the flip side — what local mode does **not** give you, and when you'd
graduate past it — see [What local mode does *not* cover](local-caveats.md).

---

## 1. What "completely locally" means

Omnigent architecture includes a few components that can be run in different modes. This guide walks you through running all components from a single machine:

- **Server** — a small FastAPI/uvicorn process that holds conversation state,
  the session database (SQLite by default), and serves the web UI. Locally it
  binds to `127.0.0.1:6767`.
- **REPL / web UI** — the client you actually interact with while using agents. The terminal REPL and
  the browser UI at `http://localhost:6767` are two views of the *same*
  session.
- **Host / runner** — the piece that actually runs the agent's terminals, shell
  commands, MCP servers, and sandboxes. Locally, that host is your own machine.

"Completely locally" means all three live on your laptop. State, execution, and
model credentials never leave the machine except for the calls your chosen
model provider requires.

There are paths you can take for this local setup, and they differ only in *which client you open first*.

### Path A — terminal-first (the fast path)

```bash
omnigent
```

That single command picks a model with you (on first run it detects an existing
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`, or a `claude` / `codex` CLI you're
logged into, and offers one as the default), starts a session in your terminal,
**and** launches the local web UI at `http://localhost:6767`. The browser view
mirrors the same session, so you can start typing in the terminal and pick it up
in the browser — or on your phone, if it's on the same network
(`http://<your-lan-ip>:6767`).

To launch a specific runtime instead of the default agent:

```bash
omnigent claude        # Claude Code, in a session your team can join
omnigent codex         # Codex
omnigent cursor        # Cursor
omnigent opencode      # OpenCode
omnigent hermes        # Hermes (Nous Research)
omnigent pi            # Pi
```

> The installer puts two names for the same CLI on your PATH: `omnigent` and
> the shorter `omni`. They're interchangeable.

Two example agents ship with Omnigent and make excellent first sessions:

```bash
omnigent run examples/polly/    # 🐙 multi-agent coding orchestrator (delegates + cross-reviews)
omnigent run examples/debby/    # 🟠🔵 two-headed brainstormer (Claude + GPT, side by side)
```

(Debby needs *both* a Claude and an OpenAI credential, since her two heads run
on different harnesses.)

### Path B — browser-first (server + host)

If you'd rather drive from the browser from the start, run the server and
register your machine as a host — in two terminals:

```bash
omnigent server start   # start the local server + web UI in the background
omnigent host ""        # (separate terminal) register THIS machine as a host
```

Then open `http://localhost:6767`, hit **New Chat**, pick your machine, and go.
Useful management commands:

```bash
omnigent server status  # is the background server up?
omnigent host status    # inspect host daemon / runner / session status
omnigent stop           # stop everything Omnigent is running on this machine
```

The distinction between A and B: `omnigent` (Path A) spawns a local server for
you behind the scenes and drops you straight into a terminal session. Path B
starts the server explicitly and leaves it running in the background so the web
UI is the primary surface. Same server, same database, same host — just a
different first click.


## 2. What running locally buys you

Local mode is not a stripped-down trial. You get most of the product:

- **The full meta-harness.** Swap or combine Claude Code, Codex, Cursor,
  OpenCode, Hermes, Pi, and your own YAML agents in one session. Ask one agent
  to review another's work; split a task across agents good at different things.
- **One session, many surfaces, in sync.** The terminal, the browser, and your
  phone (on the same Wi-Fi) all show the same live session. Start in one, pick
  up in another.
- **Real OS sandboxing (Linux/macOS).** Each agent terminal runs inside an OS
  sandbox — `bwrap` on Linux, `seatbelt` on macOS — with outbound traffic
  filtered by a proxy. On by default; nothing to deploy.
- **Policies / governance.** Approval gates, tool-call caps, and spend budgets
  all work locally. Toggle them in a session's info panel, or just ask in chat
  ("add a policy that asks me before running shell commands"). Spend caps and
  access limits ship as builtins.
- **Author your own agents.** An agent is a short YAML file (prompt + tools +
  sub-agents). Run it with `omnigent run path/to/agent.yaml`. Agents can even
  author agents — describe what you want in a chat and it writes the file.
- **Zero external dependencies for state.** SQLite database and local artifact
  storage under the Omnigent data dir. Nothing to provision, nothing to pay for
  beyond your model calls.

The headline value: **it's private and self-contained.** Your code, your
conversation history, and your execution all stay on your machine. With a local
Gateway model (Ollama/vLLM) you can run with no outbound calls at all.

---

## 3. Where local mode stops

Local mode is bounded by one fact: **a local server is only reachable on your
own network, and only while your laptop is on.** Off-network access, always-on
uptime, external teammates, SSO, and a production database all live on the other
side of a deploy.

The full list of caveats — plus a quick "is local enough?" decision guide — is
its own page: **[What local mode does *not* cover](local-caveats.md)**. When one
of those limits starts to bite, that's your cue to move to the
[Databricks track](../databricks/02-which-mode.md).

---

## Recap

- `omnigent` (or `omni`) → instant local session + web UI at
  `localhost:6767`. `omnigent server start` + `omnigent host` → browser-first.
- Local mode is the *full* product for one person on one network: meta-harness,
  multi-surface sync, sandboxing, policies, custom agents — private and
  self-contained.
- Its ceiling is reachability and uptime: off-network access, always-on
  availability, external teammates, SSO, and production databases all live on
  the other side of a **deploy** — see the
  [Databricks track](../databricks/02-which-mode.md) to pick your next step.
