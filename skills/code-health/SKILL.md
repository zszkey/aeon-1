---
name: Code Health
description: Report on TODOs, dead code, and test coverage gaps
var: ""
tags: [dev]
---
> **${var}** — Repo (owner/repo) to audit. If empty, audits all watched repos.

If `${var}` is set, only audit that repo (owner/repo format).

## Prerequisites & Data Sources

1.  **Watched Repos**: Read `memory/watched-repos.md`. If the file does not exist or is empty, terminate immediately.
2.  **Repository Access**: Use the GitHub REST API (`https://api.github.com`) to fetch repository metadata and file trees. Do NOT use local shell commands like `gh` or `git clone`.
    *   Auth: Ensure valid credentials are configured in the environment.
    *   Rate Limiting: If rate limited, wait 60 seconds and retry once. If still failing, skip that repo and log the error.

## Audit Steps

For each repo in `watched-repos.md`:

1.  **Fetch File Tree**: Retrieve the root directory tree via `GET /repos/{owner}/{repo}/git/trees/{branch}` (default branch `main` or `master`). Recursively fetch subdirectories if depth > 1 is required for context, but prioritize root-level analysis for speed.
2.  **Scan for Technical Debt**:
    *   **TODOs/FIXMEs**: Search file contents for regex patterns `\b(TODO|FIXME|HACK|XXX)\b`.
        *   *Constraint*: Only scan source code extensions: `.js`, `.ts`, `.tsx`, `.jsx`, `.py`, `.sol`, `.rs`, `.go`, `.java`, `.c`, `.cpp`, `.h`, `.hpp`.
    *   **Secrets**: Search for common patterns like `AKIA[0-9A-Z]{16}`, `sk_live_`, `password\s*=\s*['"]`, `api_key\s*=`.
    *   **Dead Code/Large Files**: Identify files larger than 500 lines. Flag files with high comment-to-code ratios (>30%) as potential dead code or documentation bloat.
3.  **Assess Test Coverage**:
    *   Check for existence of test directories/files (`test/`, `tests/`, `__tests__/`, `*.spec.ts`, `*_test.go`).
    *   If no test files exist for a significant module (e.g., >100 lines of logic), flag as "No Tests".
    *   *Note*: Do not run actual test suites. Only analyze file structure and naming conventions.

## Output Format

Compile a single Markdown report saved to `articles/code-health-${today}.md`. Use the following strict structure:

```markdown
# Code Health Report — ${today}

## Executive Summary
- Total Repos Audited: N
- Critical Issues Found: N (Secrets, High Risk)
- Low Priority Issues: N (TODOs, Style)

## Detailed Findings

### [Repo Name]
| Category | Count | Severity | Details |
| :--- | :--- | :--- | :--- |
| TODOs | N | Low | [Link to file] contains N TODOs |
| Secrets | N | **CRITICAL** | [Link to file] contains potential API key |
| Large Files | N | Medium | [File Path] is N lines long |
| Test Gaps | N | Medium | Module [Path] has no corresponding test file |

#### Specific Items
- **[File Path]**: `// TODO: Refactor this legacy function` (Line 42)
- **[File Path]**: `const apiKey = "sk_live_..."` (Line 12)

## Recommendations
1. [Actionable Item 1]
2. [Actionable Item 2]
```

## Fallback & Error Handling
- If API returns 404/403: Log to `memory/logs/${today}.md` as "Access Denied/Not Found" and skip.
- If API timeout: Retry once. If fails, skip repo.
- If `watched-repos.md` is missing: Do not generate report. Log "No watched repos configured."

## Logging
Append entry to `memory/logs/${today}.md`:
```markdown
- [Time] Code Health Audit: Scanned N repos. Found N critical issues.