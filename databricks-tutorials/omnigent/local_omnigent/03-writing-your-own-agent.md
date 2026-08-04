# Local Track — Part 3: Writing Your Own Agent

Everything so far used agents that already existed. Next let's walk through how you write one. An
Omnigent agent is just a **short YAML file** — a prompt, some tools, and
optionally sub-agents. You run it with `omnigent run path/to/agent.yaml`.

You don't even have to hand-write it: agents can author agents, so you can
describe what you want in any Omnigent chat and it writes the file. But
understanding the structure pays off, so let's build one by hand.

---

## The smallest possible agent

Create `hello.yaml`:

```yaml
name: hello
prompt: You are a helpful assistant who answers concisely.

executor:
  harness: claude-sdk
```

Run it:

```bash
omnigent run hello.yaml
```

That's a complete agent. `name` labels it, `prompt` is its instructions, and
`executor.harness` picks the runtime. With no model pinned, it uses whatever
provider you configured in `omnigent setup`.

> **Harness choices** (`executor.harness`): `claude-sdk` (alias `claude`),
> `claude-native`, `codex`, `codex-native`, `cursor`, `hermes`, `opencode`,
> `pi`, `openai-agents`, and more.
>
> **`-sdk` vs. `-native`** — same underlying tool (Claude Code, Codex),
> different way of driving it:
> - **`-sdk`** runs the harness **headless** via its programmatic SDK. Omnigent
>   drives it turn-by-turn; there's no interactive terminal. This is the default
>   for automated/background work and multi-agent setups (a supervisor spawning
>   `claude-sdk` workers), and it's what `permission_mode: auto` is designed for.
> - **`-native`** launches the harness's **real interactive TUI** — the same
>   terminal you'd get running `claude` yourself — inside the session. You can
>   watch it think, and **take over the keyboard** to steer or type directly.
>   Pick this when you want a human in the loop on a single agent.
>
> Rule of thumb: **`-sdk` for hands-off/automated, `-native` when you want to
> watch and jump in.**

---

## Adding tools

The `tools:` block is where an agent gets its abilities. Three kinds:

```yaml
name: analyst
prompt: You are a data analyst. Use your tools; don't guess.

executor:
  harness: claude-sdk

tools:
  # 1. A local Python function — schema auto-generated from the signature
  word_count:
    type: function
    callable: mypackage.mymodule.word_count

  # 2. Tools from an MCP server (a local command or a remote URL)
  docs:
    type: mcp
    url: https://example.com/mcp

  # 3. A sub-agent the supervisor can delegate to
  researcher:
    type: agent
    prompt: Search for relevant information and summarize it.
    tools:
      word_count: inherit      # pass a parent tool down to the sub-agent
```

- **`function`** — points at a dotted Python path; Omnigent builds the tool
  schema from the function signature.
- **`mcp`** — pulls in tools from any MCP server (local `command:` or remote
  `url:`).
- **`agent`** — a sub-agent your agent can hand work to. `inherit` shares a
  parent tool down into it.

---

## Skills (and how they differ from tools)

**A skill is not a tool.** Tools (above) are callable capabilities you wire into
the `tools:` block. A **skill** is a folder of instructions — a `SKILL.md` (plus
any helper files) that teaches a harness *how* to do something well, loaded into
its context on demand. Think "playbook," not "function."

Skills ride on **Claude Code's plugin convention**, so they work with the
`claude-*` harnesses. Lay them out inside your agent bundle:

```
my-agent/
  config.yaml
  .claude-plugin/
    plugin.json                 # declares the plugin (name, etc.)
  skills/
    review-prs/
      SKILL.md                  # the instructions
    triage-incidents/
      SKILL.md
```

Point the harness at the bundle so it discovers them (this is the Claude Code
`--plugin-dir` mechanism under the hood):

```yaml
executor:
  harness: claude-sdk
  config:
    plugin_dir: .               # load skills/ from this bundle
```

Inside a session the skills show up namespaced as `<agent-name>:<skill-name>`
(e.g. `my-agent:review-prs`), and the harness pulls a skill's `SKILL.md` in when
the work matches its description.

**Skills vs. tools — when to reach for which:**
- Use a **skill** to encode *procedure and judgment* — a checklist, a house
  style, a multi-step workflow the model should follow.
- Use a **tool** to give the agent a *new capability* — call an API, run a
  function, delegate to a sub-agent.

### Adding Databricks Genie MCP

Databricks Genie MCP server goes in the `tools:` block:

```yaml
tools:
  # an AI Dev Kit / DAS capability exposed over MCP
  databricks_genie:
    type: mcp
    command: <the MCP server command>     # or url: for a remote server
```

So the split is clean: **skills teach the agent your workflow; `tools:` (MCP or
`function`) give it the Databricks capabilities to execute it.**

---

## Giving it a shell and a working directory

To let an agent read/write files and run commands, declare an `os_env`. This is
what registers the `sys_os_read` / `sys_os_write` / `sys_os_edit` /
`sys_os_shell` tools (a shell comes bundled with filesystem access):

```yaml
os_env:
  type: caller_process
  cwd: .
  sandbox:
    type: none        # unsandboxed, in the current dir
```

On Linux/macOS you can instead sandbox it (`bwrap`/`seatbelt`) — see Part 1.
`sandbox: type: none` runs directly in `cwd`.

---

## Approvals & guardrails, baked in

From Part 2: you can make the agent's defaults part of the file so a new session
starts the way you want. Two layers:

```yaml
executor:
  harness: claude-native
  config:
    permission_mode: auto      # auto-approve without prompting (headless-safe)

guardrails:
  ask_timeout: 86400           # an ASK can outlive you stepping away (1 day)
  policies:
    blast_radius:
      type: function
      function:
        path: omnigent.inner.nessie.policies.blast_radius
        arguments:
          gate_pushes: false   # don't ASK on push/merge; catastrophic set still DENIED
```

This is exactly the pattern the bundled Polly sub-agents use: `permission_mode:
auto` so a headless worker never blocks on a prompt, plus a `blast_radius`
guardrail that still hard-denies the catastrophic set (force-push, `rm -rf /`,
hard-reset to a remote ref).

---

## A real multi-agent shape (learn from Polly)

The bundled **Polly** (`examples/polly/`) is the reference for a supervisor that
delegates. The pattern worth copying:

```yaml
spec_version: 1
name: polly
description: A coding orchestrator that delegates to a team of sub-agents.

spawn: true                    # can also create child sessions at runtime

executor:
  type: omnigent
  context_window: 1000000
  config:
    harness: claude-sdk

prompt: |
  You are the tech lead, not the coder. Decompose the goal, delegate every
  coding task to a sub-agent, and verify with an independent reviewer...

async: true                    # sub-agents run to completion and notify via inbox
cancellable: true
timers: true

tools:
  agents:                      # sub-agents live in agents/<name>/config.yaml
    - claude_code
    - codex
    - pi
```

Key ideas to steal:
- **A supervisor that writes nothing itself**, only plans and delegates.
- **Sub-agents in their own files** under `agents/<name>/config.yaml`, each a
  full agent with its own harness, prompt, `os_env`, and guardrails.
- **`async: true`** so workers run in parallel and wake the supervisor via its
  inbox instead of being driven turn-by-turn.
- **`spawn: true`** so the supervisor can even author and launch new agents at
  runtime.

Explore `examples/polly/` and `examples/debby/` in your install for complete,
working versions:

```bash
omnigent run examples/polly/
omnigent run examples/debby/
```

---

## Iterate fast

```bash
omnigent run hello.yaml -p "first message"   # send an opening prompt
omnigent run hello.yaml --harness codex      # try it on a different harness
omnigent run hello.yaml --model <id>         # pin a model
omnigent run hello.yaml --no-session         # throwaway session, no history
```

And the shortcut: open any Omnigent chat and say *"write me an agent that
reviews my PRs using Codex"* — it authors the YAML for you, which you then run
and refine by hand.

---

## Recap

- An agent is a YAML file: `name`, `prompt`, `executor.harness`, and optional
  `tools` / `os_env` / `guardrails`.
- Three tool kinds: local **`function`**, an **`mcp`** server, and a sub-**`agent`**.
- Declare `os_env` to give it a shell + files; set `permission_mode` and
  `guardrails` to bake in your approval defaults (Part 2).
- **Polly** and **Debby** are the reference multi-agent examples — read them,
  copy the shape.
- Next: the [full Agent YAML spec](https://github.com/omnigent-ai/omnigent/blob/main/docs/AGENT_YAML_SPEC.md).
