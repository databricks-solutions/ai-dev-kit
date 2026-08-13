# Omnigent Tutorial

A hands-on tutorial for [Omnigent](https://omnigent.ai), the open-source
**meta-harness** for AI agents (Claude Code, Codex, Cursor, OpenCode, Hermes,
Pi, and your own YAML agents).

It's split into **two tracks** — pick the one that matches how you'll
run Omnigent, or read both to understand the trade-offs.

> The Databricks experience is currently a **Beta** workspace preview.

---
##  Install
Follow instructions at [Omnigent](https://omnigent.ai) to install using `uv`, `homebrew`, or your preferred option. You can also choose to install
the desktop application and mobile app.

### Suggested install
To make sure you have dependencies to work with a Databricks managed Omnigent, you can install the additional databricks dependencies:
`uv tool install "omnigent[databricks]"`

### Verify

```bash
omnigent --version
```

Expected output:

```
omnigent x.y.z
```

If the command isn't found, try starting a new termainal session then make sure `~/.local/bin` is on your `PATH`.

## Set up

### Choosing and switching models
Start by selecting how you will connect to your LLM and agent defaults:
```bash
omnigent setup          # add/remove credentials, set per-agent defaults
```

### Smoke test

Once credentials are configured, confirm they're wired up correctly:

```bash
omnigent config list
```

Expected output (example with a Databricks credential):

```
Credential     Kind          Details
─────────────────────────────────────────────────────
my-workspace   Databricks    https://adb-xxxx.azuredatabricks.net
anthropickey   API key       Anthropic  ·  claude-sonnet-4-5
```

Each configured credential appears as a row. If a row is missing or shows an error, re-run `omnigent setup` to update it. 


Omnigent works with four credential kinds, all first-class (but each with their own cost implications):
| | Kind | What it is |
|---|---|---|
| 🎟️ | **Subscription** | A Claude Pro/Max or ChatGPT plan via the official `claude` / `codex` CLIs |
| 🧱 | **Databricks** | A Databricks workspace profile (needs the `databricks` extra) |
| 🔑 | **API key** | A first-party vendor key (Anthropic, OpenAI, …) |
| 🌐 | **Gateway** | Any OpenAI-/Anthropic-compatible `base_url` + key (OpenRouter, Ollama, LiteLLM, Azure, etc) |

Defaults are per-agent, so a Claude default and a Codex default coexist. You can
also switch mid-session with the `/model` command.

---

## Choose a Mode

Every mode is a choice of **where the server lives** (state + web UI) and
**where the host lives** (where the agent's terminals actually run):

| Mode | Server | Host | Best for |
|---|---|---|---|
| **Local** | your laptop (SQLite) | your laptop | solo, private, custom policies |
| **Databricks managed (Beta)** | Workspace-managed (Beta) | Databricks Sandbox | no local install, governed, collaborative |
| **Hybrid** | Workspace-managed (Beta) | your laptop | local runner and filesystem, access from outside local network |
| **Custom** | Custom server or Databricks App | laptop / sandbox | custom always-on team environment |

Full reasoning in section "Which Mode?" (coming soon)

---

## 🖥️ Local track — run it all on your machine

| Part | What it covers |
|---|---|
| [1 · Running locally](local_omnigent/01-running-locally.md) | Two ways to start locally, what local mode buys you, and its caveats |
| [2 · Approvals & auto-approve](local_omnigent/02-approvals-local.md) | Making the agent stop (or stop asking): per-prompt, in-session, and permanent defaults |
| [3 · Writing your own agent](local_omnigent/03-writing-your-own-agent.md) | The agent YAML anatomy: prompt, harness, tools, sub-agents, and baked-in guardrails |
| [4 · Collaboration](local_omnigent/04-collaboration.md) | Share, co-drive (`attach`), and fork a session; `run` vs `attach` vs `resume` |

**Start here if:** you're solo, want private/offline work, need custom policy
code, or just want the fastest way to understand the product.

## 🧱 Databricks track — the managed & team experience

Stay tuned.

---
