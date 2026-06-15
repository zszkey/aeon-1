#!/usr/bin/env python3
"""
Aeon Runner v3 闁?Agnes AI + 197 skills
Pure Python, zero framework deps.

Usage:
  python aeon_runner.py run <skill-name> [--var "param"]
  python aeon_runner.py list
"""

import os, sys, json, re, time, datetime, glob, urllib.request, urllib.error, urllib.parse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.join(SCRIPT_DIR, "skills")
MEMORY_DIR = os.path.join(SCRIPT_DIR, "memory")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "outputs")
LOGS_DIR = os.path.join(MEMORY_DIR, "logs")
MEMORY_MD = os.path.join(MEMORY_DIR, "MEMORY.md")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "aeon_config.json")

AGNES_URL = "https://apihub.agnes-ai.com/v1/chat/completions"
AGNES_MODEL = "agnes-2.0-flash"
MAX_TOOL_TURNS = 8
FETCH_TIMEOUT = 20
TOOL_RESULT_MAX_CHARS = 1000
EVOLVE_MAX_ATTEMPTS = 3
EVOLVE_MIN_IMPROVEMENT = 0.15
BACKUP_DIR = os.path.join(SCRIPT_DIR, ".evolve_backups")


def load_config():
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
    cfg.setdefault("model", AGNES_MODEL)
    return cfg


def get_api_key():
    cfg = load_config()
    if cfg.get("api_key"):
        return cfg["api_key"].strip()
    val = os.environ.get("AGNES_API_KEY", "") or os.environ.get("AEON_API_KEY", "")
    return val.strip()


def ensure_dirs():
    for d in [MEMORY_DIR, LOGS_DIR, OUTPUT_DIR]:
        os.makedirs(d, exist_ok=True)


def ensure_memory():
    if not os.path.exists(MEMORY_MD):
        with open(MEMORY_MD, "w", encoding="utf-8") as f:
            f.write("# MEMORY.md\n\n## Active Topics\n- (none)\n\n## Preferences\n- (none)\n")


def read_memory():
    ctx = []
    if os.path.exists(MEMORY_MD):
        with open(MEMORY_MD, "r", encoding="utf-8") as f:
            ctx.append("# MEMORY.md\n" + f.read())
    try:
        logs = sorted(os.listdir(LOGS_DIR))[-3:]
        for log in logs:
            path = os.path.join(LOGS_DIR, log)
            with open(path, "r", encoding="utf-8") as f:
                ctx.append("# " + log + "\n" + f.read())
    except:
        pass
    return "\n\n".join(ctx) if ctx else "(no memory yet)"


def extract_skill_prompt(skill_md_path, var=""):
    with open(skill_md_path, "r", encoding="utf-8") as f:
        text = f.read()
    if text.startswith("---"):
        idx = text.find("---", 3)
        if idx != -1:
            text = text[idx + 3:]
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    text = text.replace("${today}", today)
    text = text.replace("${yesterday}", (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d"))
    text = text.replace("${var}", var or "")
    text = re.sub(r'\$\{[^}]+\}', '', text)
    return text.strip()


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "HTTP GET a URL. Use for APIs, web content, data retrieval.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL"},
                    "headers_json": {"type": "string", "description": "Optional JSON headers"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web. Returns titles, snippets, URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keywords"},
                    "limit": {"type": "integer", "description": "Max results (1-10)"}
                },
                "required": ["query"]
            }
        }
    }
]


def execute_web_fetch(url, headers_json=None):
    headers = {"User-Agent": "AeonRunner/3.0"}
    if headers_json:
        try:
            headers.update(json.loads(headers_json))
        except:
            pass
    req = urllib.request.Request(url, headers=headers)
    try:
        r = urllib.request.urlopen(req, timeout=FETCH_TIMEOUT)
        ct = r.headers.get("Content-Type", "")
        raw = r.read(500_000)
        if "json" in ct:
            try: return json.dumps(json.loads(raw), ensure_ascii=False, indent=2)[:3000]
            except: pass
        return raw.decode(errors="replace")[:3000]
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500] if e.fp else ""
        return "HTTP {}: {}".format(e.code, body)
    except Exception as e:
        return "Error: " + str(e)


def execute_web_search(query, limit=5):
    limit = min(limit or 5, 10)
    try:
        url = "https://api.duckduckgo.com/?q={}&format=json&no_html=1".format(urllib.parse.quote(query))
        req = urllib.request.Request(url, headers={"User-Agent": "AeonRunner/3.0"})
        r = urllib.request.urlopen(req, timeout=15)
        data = json.loads(r.read())
        results = []
        for item in data.get("RelatedTopics", [])[:limit]:
            text = item.get("Text", "")
            href = item.get("FirstURL", "")
            if text:
                results.append("- {}\n  {}".format(text, href))
        return "\n".join(results) if results else "No results."
    except Exception as e:
        return "Search error: " + str(e)


def execute_tool(name, arguments):
    args = json.loads(arguments) if isinstance(arguments, str) else arguments
    if name == "web_fetch":
        return execute_web_fetch(args.get("url", ""), args.get("headers_json"))[:TOOL_RESULT_MAX_CHARS]
    elif name == "web_search":
        return execute_web_search(args.get("query", ""), args.get("limit", 5))[:TOOL_RESULT_MAX_CHARS]
    return "Unknown tool: " + name


def call_agnes(messages, api_key, tools=None):
    body = {"model": AGNES_MODEL, "messages": messages, "max_tokens": 8000, "temperature": 0.3}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    for attempt in range(3):
        try:
            req = urllib.request.Request(AGNES_URL, data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key})
            r = urllib.request.urlopen(req, timeout=180)
            return json.loads(r.read())
        except urllib.error.HTTPError as e:
            err = e.read().decode()[:500] if e.fp else "HTTP {}".format(e.code)
            if attempt < 2: time.sleep(2 ** attempt); continue
            raise Exception("[Agnes API {}] {}".format(e.code, err))
        except Exception as e:
            if attempt < 2: time.sleep(2 ** attempt); continue
            raise Exception("[Network] " + str(e))


def run_skill(skill_name, var="", verbose=True):
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("No API key. Set AGNES_API_KEY or add api_key to aeon_config.json")

    ensure_dirs()
    ensure_memory()

    skill_dir = os.path.join(SKILLS_DIR, skill_name)
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.exists(skill_md):
        candidates = [d for d in os.listdir(SKILLS_DIR) if skill_name.lower() in d.lower()]
        if candidates:
            skill_name = candidates[0]
            skill_dir = os.path.join(SKILLS_DIR, skill_name)
            skill_md = os.path.join(skill_dir, "SKILL.md")
        if not os.path.exists(skill_md):
            raise FileNotFoundError("Skill not found: " + skill_name)

    if verbose:
        print("\n" + "="*60)
        print("  AEON Runner v3   |   Skill: {}".format(skill_name))
        print("  Model: {}   |   {}".format(AGNES_MODEL, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        print("="*60 + "\n")

    raw_prompt = extract_skill_prompt(skill_md, var)
    memory_ctx = read_memory()

    system_prompt = """You are Aeon 闁?an autonomous AI agent. Execute the skill using REAL, CURRENT data from tools.

Skill: {skill}
Date: {date}
Variable: {var}

## Memory
{memory}

## Skill Instructions
{raw}

## Rules
- Use web_fetch / web_search for ALL data 闁?never guess
- Batch requests per turn. Stop fetching once you have enough
- Output CLEAN Markdown: ## sections, tables, bullet points
- End with ## Sources listing fetched URLs
- NO JSON, NO raw API dumps, NO process explanations
- Be concise and actionable""".format(
        skill=skill_name,
        date=datetime.datetime.now().strftime('%Y-%m-%d'),
        var=var or '(none)',
        memory=memory_ctx,
        raw=raw_prompt
    )

    messages = [
        {"role": "system", "content": "You are Aeon, an autonomous agent. Execute skills with real web data. Output clean Markdown reports."},
        {"role": "user", "content": system_prompt}
    ]

    start = time.time()
    tool_calls_made = 0
    result = ""
    elapsed = 0

    for turn in range(MAX_TOOL_TURNS + 1):
        resp = call_agnes(messages, api_key, TOOLS)
        msg = resp["choices"][0]["message"]
        finish = resp["choices"][0].get("finish_reason", "stop")

        if msg.get("tool_calls") and finish == "tool_calls":
            tool_calls_made += len(msg["tool_calls"])
            if verbose:
                for tc in msg["tool_calls"]:
                    fn = tc["function"]
                    args_short = fn['arguments'][:80].replace('\n', ' ')
                    print("  [tool] {}: {}".format(fn['name'], args_short))

            messages.append({
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": msg["tool_calls"]
            })

            for tc in msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                fn_args = tc["function"]["arguments"]
                tool_result = execute_tool(fn_name, fn_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result[:3000]
                })
            continue

        result = msg.get("content", "")
        elapsed = time.time() - start
        break

    # Fallback: force format if result is bad
    if not result or len(result.strip()) < 50 or result.strip().startswith(('[', '{')):
        tool_texts = []
        for m in messages:
            if m.get("role") == "tool":
                tool_texts.append(m.get("content", "")[:1500])
        summary = "\n---\n".join(tool_texts[-6:])
        final_msgs = [
            {"role": "system", "content": "Format the following data as a clean Markdown report. No JSON, no raw data dumps."},
            {"role": "user", "content": "Turn this into a Markdown report:\n\n" + summary[:4000]}
        ]
        resp = call_agnes(final_msgs, api_key, tools=None)
        result = resp["choices"][0]["message"].get("content", "")
        elapsed = time.time() - start

    # Save output
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    output_file = os.path.join(OUTPUT_DIR, "{}_{}.md".format(skill_name, date_str))
    header = "# {} 闁?{}\n\n> Generated {}\n> Model: {} | Time: {:.1f}s | Tool calls: {} | Var: {}\n\n---\n\n".format(
        skill_name, date_str,
        datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        AGNES_MODEL, elapsed, tool_calls_made,
        var or '(none)'
    )
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(header + result)

    # Log
    log_file = os.path.join(LOGS_DIR, "{}.md".format(date_str))
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("\n### {}\n- Time: {}\n- Var: {}\n- Duration: {:.1f}s\n- Tool calls: {}\n- Output: {}\n".format(
            skill_name,
            datetime.datetime.now().strftime('%H:%M:%S'),
            var or '(none)', elapsed, tool_calls_made, output_file
        ))

    if verbose:
        print("\n  [OK] Done in {:.1f}s 闁?{} tool calls".format(elapsed, tool_calls_made))
        print("  [SAVE] {}".format(output_file))
        print("\n" + "-"*60)
        print(result[:1200])
        if len(result) > 1200:
            print("\n  ... ({} chars total)".format(len(result)))
        print("-"*60 + "\n")

    return output_file, result, tool_calls_made, elapsed


# ====== Self-Evolution Engine ======

def score_output(content, tool_calls, duration):
    """Rate an output 0-100: stricter calibration for meaningful improvement."""
    score = 30
    text = content or ""
    l = len(text)
    # Length: strict tiers
    if l >= 5000:  score -= 10  # fluff
    elif l >= 3000: score += 12
    elif l >= 1500: score += 8
    elif l >= 800:  score += 4
    elif l >= 400:  score += 1
    else:           score -= 25  # near-empty -> fail hard
    # Structure
    headings = text.count("## ")
    score += min(headings * 3, 12)
    if "| " in text and " |" in text:
        score += 5
    bullets = len(re.findall(r'^[*-] ', text, re.MULTILINE))
    score += min(bullets, 8)
    # Data: URLs, numbers
    urls = len(re.findall(r'https?://\S+', text))
    score += min(urls * 3, 12) if urls >= 2 else (urls * 2)
    numbers = len(re.findall(r'\d+\s*(%|USD|ETH|BTC|million|billion)', text))
    score += min(numbers * 2, 6)
    # Tool efficiency
    if tool_calls >= 8:  score += 5
    elif tool_calls >= 3: score += 3
    elif tool_calls == 0: score -= 15
    if duration < 5 and l < 200:
        score -= 20
    return max(0, min(100, score))


def find_weakest_skill():
    """Scan outputs/ to find the skill with the lowest-quality recent run."""
    ensure_dirs()
    files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "*_*.md")), key=os.path.getmtime)
    if not files:
        print("  No output files to analyze. Run some skills first.")
        return None, None
    # Group latest per skill
    latest = {}
    for f in files:
        name = os.path.basename(f)
        # Format: skillname_YYYY-MM-DD.md
        parts = name.rsplit("_", 1)
        skill = parts[0] if len(parts) == 2 else name.replace(".md", "")
        latest[skill] = f
    scored = []
    for skill, path in latest.items():
        try:
            with open(path, "r", encoding="utf-8") as fp:
                content = fp.read()
            # Extract metadata from header line
            tc_match = re.search(r'Tool calls: (\d+)', content)
            dur_match = re.search(r'Time: ([\d.]+)s', content)
            tools = int(tc_match.group(1)) if tc_match else 0
            dur = float(dur_match.group(1)) if dur_match else 60
            # Strip header for content scoring
            body = content.split("---\n", 2)[-1] if "---\n" in content else content
            s = score_output(body, tools, dur)
            scored.append((s, skill, path))
            print("  Score {:3d} | {}".format(s, skill))
        except Exception as e:
            print("  Skip {}: {}".format(skill, e))
    if not scored:
        return None, None
    scored.sort()
    weakest = scored[0]
    print("\n  Weakest: {} (score {})\n".format(weakest[1], weakest[0]))
    return weakest[1], weakest[2]


def generate_improved_prompt(original_md_path, api_key):
    """Ask Agnes: analyze this skill and suggest a better version."""
    with open(original_md_path, "r", encoding="utf-8") as f:
        original = f.read()
    skill_name = os.path.basename(os.path.dirname(original_md_path))
    # Read recent output for context
    out_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "{}_*.md".format(skill_name))), key=os.path.getmtime)
    recent_output = ""
    if out_files:
        with open(out_files[-1], "r", encoding="utf-8") as f:
            recent_output = f.read()[:3000]
    prompt = """You are a skill optimizer. Analyze this skill and its recent output, then produce an IMPROVED version.

## Original Skill (SKILL.md)
```
{original}
```

## Recent Output
```
{recent}
```

## Your Task
1. Identify 2-3 weaknesses in the current skill (vague instructions, bad data sources, poor structure)
2. Rewrite the SKILL.md to fix them. Follow these rules:
   - Keep frontmatter (--- blocks) identical
   - Make instructions MORE SPECIFIC: name exact URLs/APIs to use
   - Demand concrete output format: tables, named sections, numbers
   - Add fallback: what to do if APIs fail
   - NO GitHub-specific commands (gh, ./notify)
   - Output only the rewritten SKILL.md, nothing else

## Rewritten SKILL.md:""".format(original=original, recent=recent_output[:2000] if recent_output else "(no recent output)")
    messages = [
        {"role": "system", "content": "You rewrite skill prompts to be more specific and effective. Output only the new SKILL.md."},
        {"role": "user", "content": prompt}
    ]
    resp = call_agnes(messages, api_key, tools=None)
    improved = resp["choices"][0]["message"].get("content", "")
    # Clean: strip markdown code fences if present
    improved = re.sub(r'^```\w*\n?', '', improved.strip())
    improved = re.sub(r'\n?```$', '', improved)
    return improved.strip()


def evolve_skill(skill_name):
    """Self-evolve one skill: analyze, improve, A/B test, keep winner."""
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("No API key")
    ensure_dirs()
    os.makedirs(BACKUP_DIR, exist_ok=True)
    skill_dir = os.path.join(SKILLS_DIR, skill_name)
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.exists(skill_md):
        print("Skill '{}' not found.".format(skill_name))
        return

    print("=" * 60)
    print("  AEON Self-Evolution  |  Target: {}".format(skill_name))
    print("=" * 60)

    # Phase 1: Baseline
    print("\n[Phase 1] Running baseline...")
    base_file, base_result, base_tools, base_dur = run_skill(skill_name, verbose=False)
    base_score = score_output(base_result, base_tools, base_dur)
    print("  Baseline score: {}/100".format(base_score))

    # Phase 2: Generate improved prompt
    print("\n[Phase 2] Generating improved version...")
    improved_prompt = generate_improved_prompt(skill_md, api_key)
    if len(improved_prompt) < 50:
        print("  Failed to generate meaningful improvement. Aborting.")
        return
    print("  Improved prompt: {} chars".format(len(improved_prompt)))

    # Phase 3: Backup original, write improved
    backup_path = os.path.join(BACKUP_DIR, "{}_{}.bak".format(skill_name, datetime.datetime.now().strftime('%Y%m%d_%H%M%S')))
    with open(skill_md, "r", encoding="utf-8") as f:
        original_content = f.read()
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(original_content)
    with open(skill_md, "w", encoding="utf-8") as f:
        f.write(improved_prompt)
    print("  Backup saved to {}".format(backup_path))

    # Phase 4: Run improved version
    print("\n[Phase 4] Running improved version...")
    improved_file, improved_result, impr_tools, impr_dur = run_skill(skill_name, verbose=False)
    improved_score = score_output(improved_result, impr_tools, impr_dur)
    print("  Improved score: {}/100".format(improved_score))

    # Phase 5: Compare and decide
    print("\n[Phase 5] A/B Comparison:")
    print("  Baseline : {:3d}/100  ({})".format(base_score, base_file))
    print("  Improved : {:3d}/100  ({})".format(improved_score, improved_file))
    delta = improved_score - base_score
    print("  Delta    : {:+d}".format(delta))

    if delta >= EVOLVE_MIN_IMPROVEMENT * 100:
        print("\n  >>> KEEPING improved version (+{} points)".format(delta))
        print("  >>> Backup at {}".format(backup_path))
        result = "kept_improved"
    elif delta > 0:
        print("\n  >>> Marginal improvement (+{}), keeping anyway".format(delta))
        result = "kept_improved"
    else:
        print("\n  >>> REVERTING to original (delta: {})".format(delta))
        with open(skill_md, "w", encoding="utf-8") as f:
            f.write(original_content)
        os.remove(backup_path)
        result = "reverted"

    # Log evolution
    log_file = os.path.join(LOGS_DIR, "{}.md".format(datetime.datetime.now().strftime('%Y-%m-%d')))
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("\n### evolve:{}\n- Result: {}\n- Baseline: {} -> Improved: {}\n- Delta: {:+d}\n".format(
            skill_name, result, base_score, improved_score, delta))
    print("\n  Evolution complete. Result: {}".format(result))


def evolve_loop(max_skills=3):
    """Auto-evolve: find weakest skills, try to improve each."""
    print("\n" + "=" * 60)
    print("  AEON Self-Evolution Loop")
    print("  Max skills: {} | Min improvement: {:.0%}".format(max_skills, EVOLVE_MIN_IMPROVEMENT))
    print("=" * 60)

    # Collect all skills with outputs
    ensure_dirs()
    out_files = sorted(glob.glob(os.path.join(OUTPUT_DIR, "*_*.md")), key=os.path.getmtime)
    latest = {}
    for f in out_files:
        name = os.path.basename(f)
        parts = name.rsplit("_", 1)
        skill = parts[0] if len(parts) == 2 else name.replace(".md", "")
        latest[skill] = f
    if not latest:
        print("No outputs to analyze. Run at least one skill first.")
        return

    # Score all
    scored = []
    print("\nScoring {} skills with outputs:\n".format(len(latest)))
    for skill, path in latest.items():
        try:
            with open(path, "r", encoding="utf-8") as fp:
                content = fp.read()
            tc_match = re.search(r'Tool calls: (\d+)', content)
            dur_match = re.search(r'Time: ([\d.]+)s', content)
            tools = int(tc_match.group(1)) if tc_match else 0
            dur = float(dur_match.group(1)) if dur_match else 60
            body = content.split("---\n", 2)[-1] if "---\n" in content else content
            s = score_output(body, tools, dur)
            scored.append((s, skill, path))
            print("  {:3d}  {}".format(s, skill))
        except Exception as e:
            print("  ERR  {}: {}".format(skill, e))

    scored.sort()
    improved_count = 0
    for score, skill, path in scored[:max_skills]:
        if score >= 70:
            print("\n  Skill '{}' already good ({}). Skipping.".format(skill, score))
            continue
        print("\n--- Evolving {} (score: {}) ---".format(skill, score))
        try:
            evolve_skill(skill)
            improved_count += 1
        except Exception as e:
            print("  Evolve failed: {}".format(e))

    print("\n" + "=" * 60)
    print("  Evolution loop done. Improved {} skills.".format(improved_count))
    print("=" * 60)


def list_skills():
    if not os.path.exists(SKILLS_DIR):
        print("No skills directory found.")
        return
    skills = []
    for d in sorted(os.listdir(SKILLS_DIR)):
        md = os.path.join(SKILLS_DIR, d, "SKILL.md")
        if not os.path.exists(md): continue
        desc = ""
        try:
            with open(md, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("description:"):
                        desc = line.replace("description:", "").strip().strip('"\'')
                        break
        except: pass
        skills.append((d, desc))

    print("\n  {} skills available:\n".format(len(skills)))
    for name, desc in skills:
        print("  {:<35s} {}".format(name, desc[:60]))


def main():
    if len(sys.argv) < 2:
        print("AEON Runner v3")
        print("  python aeon_runner.py run <skill> [--var VAL]")
        print("  python aeon_runner.py list")
        print("  python aeon_runner.py evolve <skill>")
        print("  python aeon_runner.py auto-evolve")
        print("  python aeon_runner.py score")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "list":
        list_skills()
    elif cmd == "score":
        find_weakest_skill()
    elif cmd == "evolve":
        if len(sys.argv) < 3:
            print("Usage: python aeon_runner.py evolve <skill>")
            sys.exit(1)
        evolve_skill(sys.argv[2])
    elif cmd == "auto-evolve":
        evolve_loop()
    elif cmd == "run":
        if len(sys.argv) < 3:
            print("Usage: python aeon_runner.py run <skill> [--var VAL]")
            sys.exit(1)
        skill = sys.argv[2]
        var = ""
        for i, a in enumerate(sys.argv):
            if a == "--var" and i + 1 < len(sys.argv):
                var = sys.argv[i + 1]
        run_skill(skill, var)
    else:
        print("Unknown: " + cmd)


if __name__ == "__main__":
    main()
