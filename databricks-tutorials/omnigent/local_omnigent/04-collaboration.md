# Local Track — Part 4: Collaborate — Share, Co-Drive, Fork

An Omnigent session isn't just yours to watch — it's a live surface other people
can join. This part covers the three ways to work together on a session, and the
`attach` / `resume` / `--fork` commands behind them.

> **There is no "view-only" mode.** Every way of bringing someone into a live
> session is *collaborative* — even **Share** lets them chat with the agent, and
> **attach** hands them a live keyboard on your host. If you need someone to
> only observe, the closest thing is Share plus simply not typing — but assume
> anyone in the session can act, not just watch.

> **Reachability first.** Everything here works locally *for people who can reach
> your server*. On your own Wi-Fi that's your LAN address
> (`http://192.168.x.x:6767`); for teammates off your network you need a deployed
> host (local track Part 1, or the Databricks track). Turn on multi-user accounts
> with `OMNIGENT_AUTH_ENABLED=1 omnigent server start`, then invite via
> **Admin → Members → Invite**.

---

## The three modes at a glance

| Mode | Who runs the work | Best for |
|---|---|---|
| **Share** | you (they watch + chat) | demoing, a teammate observing live |
| **Co-drive** | you (their messages run on *your* machine) | pairing, handing the keyboard to an expert |
| **Fork** | them (a copy on *their* machine) | branching off to explore independently |

The dividing line is **whose machine executes**. Share and co-drive both run on
*your* host; fork clones the conversation so it runs on *theirs*.

---

## 1. Share a live session (watch + chat)

In the web UI, hit **Share** and send the link. Teammates open it and watch your
agent work in real time — messages, sub-agents, terminals, and files stream to
them. They can chat with the agent too. The execution still happens on your
host; they're looking through a window.

Great for: a live demo, a code walkthrough, or someone keeping an eye on a
long-running task.

## 2. Co-drive (their input, your machine)

A teammate can **co-attach** to your running session so their messages execute
on **your** machine. From their terminal:

```bash
omnigent attach <conversation_id>
# against a specific server:
omnigent attach <conversation_id> --server https://<your-host>
```

`attach` is a *thin client*: it joins an already-**live** conversation and
streams its I/O. It never starts a server, runner, or harness — and it errors
loudly if there's nothing live to attach to. (To *start* a session use
`omnigent run`; to reopen a stored one use `omnigent resume`.)

Great for: pairing, or handing the keyboard to a domain expert mid-investigation
without them having to reproduce your environment.

## 3. Fork (a copy on their machine)

Forking clones the conversation up to a point and continues **independently** on
the forker's own machine:

```bash
omnigent run --fork <conversation_id>
```

There's also a **`/fork`** slash command inside the REPL to fork the current
conversation into a new session. After a fork, the two histories diverge — your
original is untouched.

Great for: "let me take this thread and try a different approach" without
disturbing the original session.

---

## Reopening vs. joining (don't mix these up)

Three verbs, three meanings:

- **`omnigent run`** — *start* a new session (spawns server/runner/harness).
- **`omnigent attach <id>`** — *join* a session that is **live right now**.
  Applies no defaults; pure client.
- **`omnigent resume <id>`** — *reopen* a **stored** conversation, auto-routing
  by runtime (a `claude-native` session lands in `omnigent claude`; others hint
  `omnigent run --resume <id> <agent.yaml>`). Bare `omnigent resume --server …`
  opens a cross-agent picker over your prior conversations.

Rule of thumb: **attach** if it's running, **resume** if it's parked, **run
--fork** if you want your own copy.

---

## A typical pairing flow

```bash
# You — start a shared session and turn on accounts so a teammate can sign in
OMNIGENT_AUTH_ENABLED=1 omnigent server start
omnigent claude                     # start working; hit Share in the web UI

# Teammate (on your network, signed in via your invite) — co-drive it
omnigent attach conv_abc123 --server http://192.168.1.50:6767

# Teammate wants to branch off on their own machine instead
omnigent run --fork conv_abc123
```

---

## Recap

- **Share** = they watch and chat; **co-drive** (`attach`) = their input runs on
  your machine; **fork** (`run --fork` / `/fork`) = they get an independent copy.
- **`attach`** joins a *live* session; **`resume`** reopens a *stored* one;
  **`run`** starts a new one.
- All of this is gated by **reachability** — fine on your LAN, but true
  off-network collaboration needs a deployed host (Databricks track).
