# Omnigent Tutorial

A hands-on tutorial for [Omnigent](https://omnigent.ai), the open-source
**meta-harness** for AI agents (Claude Code, Codex, Cursor, OpenCode, Hermes,
Pi, and your own YAML agents).

It's split into **two tracks** — pick the one that matches how you'll
run Omnigent, or read both to understand the trade-offs.

> The Databricks experience is currently a **Beta** workspace preview.

---

## 🖥️ Local track — run it all on your machine

| Part | What it covers |
|---|---|
| [1 · Running locally](local/01-running-locally.md) | Two ways to start locally, what local mode buys you, and its caveats |
| [2 · Approvals & auto-approve](local/02-approvals-local.md) | Making the agent stop (or stop asking): per-prompt, in-session, and permanent defaults |
| [3 · Writing your own agent](local/03-writing-your-own-agent.md) | The agent YAML anatomy: prompt, harness, tools, sub-agents, and baked-in guardrails |
| [4 · Collaboration](local/04-collaboration.md) | Share, co-drive (`attach`), and fork a session; `run` vs `attach` vs `resume` |

**Start here if:** you're solo, want private/offline work, need custom policy
code, or just want the fastest way to understand the product.

## 🧱 Databricks track — the managed & team experience

Stay tuned.

---

## The one-diagram summary

Every mode is a choice of **where the server lives** (state + web UI) and
**where the host lives** (where the agent's terminals actually run):

| | Server | Host | Best for |
|---|---|---|---|
| **Local** | your laptop (SQLite) | your laptop | solo, private, custom policies |
| **Databricks Sandbox** | managed | serverless sandbox | zero-install trial, laptop-free, governed |
| **Your own Databricks App** | your App (Lakebase) | laptop / sandbox / managed host | always-on team tool |

Full reasoning in [Databricks track, Part 2](databricks/02-which-mode.md).
