---
name: Priority Brief
description: Priority-driven briefing — the 3 things to focus on, why now, and what moved
var: ""
tags: [meta]
requires: []
---
<!-- autoresearch: variation C — robust, API-first, structured output -->

> **${var}** — Area to emphasize. If empty, covers all areas.

A good brief is a **priming document**, not a news dump. Every line must answer "so what?".

Today is ${today}. Read `memory/MEMORY.md`, `memory/logs/${yesterday}.md` (and today's if it exists), and `memory/cron-state.json` (if present).

## Steps

### 1. Rank, don't aggregate

Collect candidate items from:
- MEMORY.md "Next Priorities"
- Yesterday's log: unfinished work, follow-ups, notes
- Pending repo items: Fetch open PRs and Issues via GitHub REST API (`https://api.github.com/repos/{owner}/{repo}/pulls?state=open` and `/issues?state=open`) using the configured token. Filter for assignee `@me` or relevant labels.
- `memory/cron-state.json`: skills with `consecutive_failures >= 2` or `success_rate < 0.8`
- `aeon.yml`: skills whose cron matches today

Score each candidate on **leverage × urgency**:
- Leverage = does progressing this change the next 7 days?
- Urgency = does delay today make it worse?

Keep at most **3 focus items**. Everything else either goes in "Since yesterday" or is dropped. If ${var} is set, bias ranking toward that area but do not force a focus item if nothing qualifies.

### 2. Headlines — only if they change priorities

Use `WebSearch` or `WebFetch` to find 2 headlines in the user's tracked areas (AI and crypto by default; emphasize ${var} if set).
- **Sources:** Prioritize reputable tech/finance outlets (e.g., Ars Technica, The Verge, CoinDesk, Bloomberg). Avoid aggregators that return only metadata.
- **Validation:** Include a headline **only if** it meaningfully updates one of the 3 focus items, flags a new risk, or implies an action (a deadline, a market move, a shipped competitor, a disclosed exploit).
- **Fallback:** If `WebSearch` fails or returns low-quality snippets (e.g., bot detection pages, 502 errors, empty RSS feeds), skip the Watch section entirely. Do not hallucinate news.

### 3. Format — terse, scannable, opinionated

Output the following Markdown structure exactly:

```markdown
# Priority Brief — ${today}

## Focus Today
| # | Item | Why Now (≤12 words) |
|---|------|---------------------|
| 1 | [Item Name] | [Reason] |
| 2 | [Item Name] | [Reason] |
| 3 | [Item Name] | [Reason] |

## Since Yesterday
- [Moved]: [What changed] ([Link])
- [Stuck]: [What's blocked, on whom] ([Link])

## Watch
- [Headline]: [Implication for Focus #N]

## Running Today
- [Skill Name] @ [HH:MM UTC]
```

Style rules:
- Every focus item must have a "Why Now" reason. If you can't provide one, demote it.
- "Since yesterday" is ≤5 bullets; merge duplicates across sources.
- No throat-clearing. Lead with the H1 header.
- No empty sections — omit the section header if there is no content.
- If fewer than 3 candidates survive the why-now bar, allow **up to 1 background item** in the table (tagged `background:` in the "Why Now" column) so the brief still surfaces something worth knowing on quiet days. Never invent items.
- If soul files under `soul/` are populated, match that voice; otherwise keep it direct and neutral (per CLAUDE.md).

### 4. Save and Notify

- **Save:** Append to `memory/logs/${today}.md` under a `### priority-brief` heading: timestamp, the 3 focus items (one line each), headline count, and any skills flagged from cron-state. This becomes tomorrow's "since yesterday" input.
- **Notify:** Output the final Markdown text clearly labeled as `OUTPUT_START` and `OUTPUT_END` for the agent to capture. Do not use shell commands like `./notify` or `curl` directly in the thought process; rely on the platform's notification capabilities or standard output.

## Sandbox note

The sandbox may block outbound network access.
1. **GitHub:** Use the built-in `github_api` tool or environment variables if available. If not, assume no new PR/Issue data is fetched and rely on local memory/logs.
2. **Web Search/Fetch:** Use the provided `WebSearch` and `WebFetch` tools. If they fail, proceed with local data only and note "No external news available" in the Watch section (or omit Watch).
3. **Email:** Do not attempt to send emails directly via code execution unless explicitly instructed by the platform. Rely on the platform's notification system.