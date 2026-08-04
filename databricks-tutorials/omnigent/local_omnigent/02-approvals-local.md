# Local Track — Part 2: Approvals & Auto-Approve

By default, an Omnigent agent just runs. It only stops to ask permission when an
**ask-policy** is attached to the session. So "controlling approvals" comes down
to one question: *is there an ask-policy, and how strict is it?*

This part shows the four ways to loosen approvals locally, from "right now, this
prompt" to "forever, on every new session."

---

## The mental model (read this once)

```
No ask-policy attached        →  agent runs, never pauses
Ask-policy attached (e.g.     →  agent PAUSES before shell/file actions
  "ask before shell/files")      and waits for your y / a / n
```

There are two independent knobs:

1. **Omnigent policies** — the `ASK` gate described above. Lives in the session.
2. **The harness `permission_mode`** — whether the underlying CLI (Claude Code,
   Codex, …) *also* asks on its own. Lives in the agent's YAML.

"Fully open" means: no ask-policy **and** a permissive `permission_mode`.

---

## 1. Answer a single prompt (right now)

When the agent pauses, you'll see an approval prompt. Type:

| You type | What happens |
|---|---|
| `y` (or `yes`, `ok`, `approve`) | **Approve once** — just this one action |
| `a` (or `always`) | **Approve *and stop asking*** for this kind of action, for the rest of the session |
| anything else / `n` | **Deny** — the action is blocked |

`a` is the quickest "save my approval": the agent remembers that you said always
for this policy and won't prompt again for the same kind of action.

> **Scope:** the `a` / "always" memory is **per-session**. Start a fresh session
> and the prompt comes back. For a permanent default, see section 4.

---

## 2. Change the rule mid-session, by just asking

You don't have to hunt for a setting. In the chat, tell the agent:

> *"Stop asking me before running shell commands."*

The agent edits the session's policies for you (it has a `sys_add_policy` tool
and can list what's available). You can also go the other way — *"ask me before
any file writes"* — to make a running session **stricter**.

---

## 3. Toggle it in the web UI

Open the session's **info panel** (`http://localhost:6767`) → the policies list.
Toggle the ask-policy **off** to stop the prompts, or **on** to add them. This is
the same set of policies, just a click instead of a sentence.

---

## 4. Set the default for every NEW session (durable)

The three options above all live inside *one* session. To make new sessions open
from the start, set it in the agent's YAML — this is the real "save my prior
approval as part of session initialization":

```yaml
executor:
  harness: claude-sdk
  config:
    permission_mode: acceptEdits    # auto-approve file edits; still asks on riskier things
    # permission_mode: bypassPermissions   # auto-approve EVERYTHING
```

`permission_mode` accepts: `auto` (the default), `default`, `acceptEdits`,
`bypassPermissions`, `plan`, `dontAsk`.

And **don't attach** an `ask_on_os_tools` policy (i.e. leave the `policies:`
block for approvals out). With both of those, a new session runs without ever
prompting.

> **Important interaction:** `acceptEdits` / `bypassPermissions` silence the
> *harness's own* prompt, but they do **not** override an Omnigent `ASK` policy.
> If a session- or server-level ask-policy is attached, it still fires. Truly
> silent = permissive `permission_mode` **and** no ask-policy.

Project vs. user scope works like git: `.omnigent/config.yaml` in your current
directory overrides `~/.omnigent/config.yaml`, so you can make "open by default"
a per-project choice.

---

## Quick reference

| I want to… | Do this | Lasts |
|---|---|---|
| Approve this one action | type `y` | one action |
| Approve and stop asking (this kind) | type `a` | this session |
| Loosen/tighten a running session | ask in chat, or web UI toggle | this session |
| New sessions open by default | `permission_mode` in YAML + no ask-policy | permanent |

---

## Recap

- Prompts only exist because an **ask-policy** is attached; loosening approvals
  means relaxing or removing it.
- **In-session:** `a` to stop asking, ask in chat, or toggle in the web UI.
- **Forever:** set `permission_mode` in the agent YAML and omit the ask-policy.
- Local mode gives you full control over the policy *code* itself. On Databricks
  you get the same idea but only the **built-in** policies, toggled from the
  workspace UI — covered in the Databricks track.
