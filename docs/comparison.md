# AgentGuard vs. Related Projects

AgentGuard occupies a different niche from the larger AI assistant and agent orchestration platforms. This document explains how it differs and where it complements them.

## Overview

| Dimension | OpenClaw | Ruflo | AgentGuard |
| --- | --- | --- | --- |
| Primary purpose | Personal AI assistant platform | Multi-agent orchestration | Claude Code asset management |
| Language | TypeScript | TypeScript | Python |
| What it manages | Channels, sessions, agents, plugins | Agent swarms, memory, task routing | .claude/ assets (agents, skills, hooks, commands, rules) |
| Relationship to Claude Code | Independent platform (multi-provider) | Orchestration layer on top of Claude Code | Asset lifecycle tool for Claude Code |
| Security model | DM pairing, sandbox mode, tool gating | Input validation, prompt injection defense | Static analysis scanner, trust levels, import gates |
| Scale target | Single user, multi-device, multi-channel | Teams/enterprise, multi-agent swarms | Individual developer or team, multi-repo |

## What Each Project Does

### OpenClaw

OpenClaw is a personal AI assistant platform with a multi-channel inbox spanning WhatsApp, Telegram, Slack, Discord, Signal, and more. It provides a gateway architecture with WebSocket control plane, a skills marketplace (ClawHub), multi-agent routing, voice wake, and companion apps across platforms. It is a full AI assistant runtime — not specific to Claude Code.

### Ruflo

Ruflo is a multi-agent orchestration platform for Claude Code. It coordinates 100+ specialized agents in swarm topologies (queen/workers or mesh), with self-learning adaptation, vector memory, knowledge graphs, and intelligent task routing. It provides a plugin SDK with a decentralized marketplace. Ruflo sits on top of Claude Code as an orchestration layer.

### AgentGuard

AgentGuard is a CLI tool for managing the configuration files that tools like Claude Code produce and consume. It inventories `.claude/` directories, catalogs assets, profiles usage from session transcripts, extracts reusable patterns, evaluates quality, and detects security issues. AgentGuard is not an AI assistant or agent orchestrator — it manages the assets those systems use.

## How They Complement Each Other

AgentGuard is complementary to both OpenClaw and Ruflo rather than competitive:

- **OpenClaw + AgentGuard**: OpenClaw's workspace skills follow similar patterns to Claude Code assets. AgentGuard could audit, version, and quality-check OpenClaw skills alongside Claude Code assets.

- **Ruflo + AgentGuard**: Ruflo-managed agents and skills live in `.claude/` directories. AgentGuard can inventory, security-scan, and evaluate those assets regardless of whether they were created by Ruflo or by hand.

- **General principle**: Any tool that creates or manages `.claude/` files produces assets that AgentGuard can audit. AgentGuard's security scanner works on any `.claude/` directory regardless of which tool created it.

## Key Differences

1. **AgentGuard does not run agents.** It manages the configuration files that agent runtimes read. It's closer to a package manager or linter than an AI platform.

2. **AgentGuard works across repos.** Pattern extraction scans your entire catalog to find what works and replicate it. This cross-repo view is unique to asset management tools.

3. **AgentGuard adds a security layer.** The static analyzer, trust model, and import gates provide security assurance that neither OpenClaw nor Ruflo focus on for asset files specifically.

4. **AgentGuard measures quality from telemetry.** Per-asset metrics from actual session data, regression detection, and A/B testing provide evidence-based asset improvement.

## When to Use What

| Goal | Tool |
| --- | --- |
| Build an AI assistant with multi-channel messaging | OpenClaw |
| Orchestrate multiple Claude Code agents in swarms | Ruflo |
| Audit, version, and improve your .claude/ configuration files | AgentGuard |
| Security-scan imported agents/skills before use | AgentGuard |
| Compare asset versions with A/B testing | AgentGuard |
| Extract patterns from your best assets and replicate them | AgentGuard |
