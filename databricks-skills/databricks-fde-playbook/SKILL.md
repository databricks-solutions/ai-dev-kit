---
name: databricks-fde-playbook
description: "FDE engagement best practices for Databricks: Git workflow, code quality, architecture, platform usage, CI/CD, testing, and production handoff. Use when working on Databricks FDE engagements or building production-ready Databricks solutions."
---

# FDE Technical Playbook

A practical guide for how FDE teams write code, collaborate, and ship production-ready solutions on Databricks — from environment setup to customer handoff.

## Core Philosophy

- **Platform-First:** Default to Databricks platform features before building custom solutions. Document all platform gaps for R&D feedback.
- **Build for Handoff:** Every line of code, architecture decision, and configuration should anticipate customer ownership.
- **Leave It Better:** Actively improve what you touch — this compounds value across engagements.
- **System Design = Implementation Quality:** Thoughtful architecture matters as much as clean, tested code.

## Reference Files

- **[1-foundations-and-setup.md](1-foundations-and-setup.md)** — Dev environment (uv, Ruff, CLI, IDE), Git workflow, daily dev cycle
- **[2-code-quality.md](2-code-quality.md)** — Python standards, documentation, naming, error handling, code simplicity, logging, testing
- **[3-architecture.md](3-architecture.md)** — Design principles, project structure, code organization, config management, resilience, API design, versioning
- **[4-databricks-platform.md](4-databricks-platform.md)** — Notebooks, DABs, Unity Catalog, compute, data engineering patterns, resource management, security
- **[5-productionization.md](5-productionization.md)** — Observability, CI/CD, environment strategy, documentation, handoff checklist

## Quick Reference

| Topic | File | Section |
|-------|------|---------|
| uv / Ruff setup | [1-foundations-and-setup.md](1-foundations-and-setup.md) | §2 Dev Environment |
| Git branch naming | [1-foundations-and-setup.md](1-foundations-and-setup.md) | §3.2 Branch Strategy |
| PR workflow | [1-foundations-and-setup.md](1-foundations-and-setup.md) | §3.4–3.6 Pull Requests |
| Python type hints / docstrings | [2-code-quality.md](2-code-quality.md) | §4.1–4.2 |
| Testing philosophy | [2-code-quality.md](2-code-quality.md) | §4.7 Testing |
| Project structure | [3-architecture.md](3-architecture.md) | §6.2 Project Structure |
| Config management pattern | [3-architecture.md](3-architecture.md) | §6.4 Config Management |
| Idempotent writes | [4-databricks-platform.md](4-databricks-platform.md) | §8.1 |
| Medallion architecture | [4-databricks-platform.md](4-databricks-platform.md) | §8.2 |
| CI/CD pipeline setup | [5-productionization.md](5-productionization.md) | §12 CI/CD |
| Production readiness | [5-productionization.md](5-productionization.md) | §13.4 Checklist |

## Related Skills

- **[databricks-asset-bundles](../databricks-asset-bundles/SKILL.md)** — DABs YAML reference (jobs, pipelines, dashboards)
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** — Python SDK implementation reference
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — Unity Catalog operations and system tables
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — Job orchestration patterns
