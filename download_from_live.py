#!/usr/bin/env python3
"""
从线上 Vercel 后端下载所有已有的项目数据到本地。

用法:
  1) 打开浏览器 -> F12 -> Console -> 输入: localStorage.getItem('clawthon_token')
  2) 复制引号内的 token
  3) 运行: python download_from_live.py --token "eyJ..."

或直接运行（只拉不需要认证的产品数据）:
  python download_from_live.py
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

LIVE_API = "https://clawthon-towow-api.vercel.app"
EXPORT_DIR = Path("D:/Clawthon/exports/live_download")


def fetch(url, token=None, method="GET", data=None, timeout=30):
    """Fetch from URL with optional auth. Returns (data, error)."""
    headers = {}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers)
    if method != "GET":
        req.method = method
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        raw = resp.read().decode("utf-8")
        ct = resp.headers.get("Content-Type", "")
        if "json" in ct or raw.startswith("[") or raw.startswith("{"):
            try:
                return json.loads(raw), None
            except json.JSONDecodeError:
                return raw, None
        return raw, None  # HTML or plain text
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:300]
        return None, f"HTTP {e.code}: {err_body[:120]}"
    except Exception as e:
        return None, str(e)


def main():
    parser = argparse.ArgumentParser(description="Download Clawthon data from live Vercel")
    parser.add_argument("--token", default="", help="JWT token (from browser localStorage)")
    parser.add_argument("--output", default=str(EXPORT_DIR), help="Output directory")
    args = parser.parse_args()

    token = args.token.strip().strip('"').strip("'")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    batch_dir = Path(args.output) / f"batch_{ts}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("  Clawthon - Download ALL data from live Vercel backend")
    print(f"  API:   {LIVE_API}")
    print(f"  Token: {'YES' if token else 'NO (only public data)'}")
    print(f"  Save:  {batch_dir}")
    print("=" * 65)

    all_projects = {}   # id -> data
    all_products = []
    all_events = []

    # Warm up Vercel serverless (cold start takes ~5s)
    print("\n[0] Warming up Vercel...")
    for attempt in range(3):
        _, err = fetch(f"{LIVE_API}/health", timeout=15)
        if err is None:
            print("    Backend is warm")
            break
        print(f"    Attempt {attempt+1}: {err}")
        import time; time.sleep(2)

    # ================================================================
    # STEP 1: Sandbox products (no auth, with retry)
    # ================================================================
    print("\n[1] Sandbox products...")
    for attempt in range(3):
        data, err = fetch(f"{LIVE_API}/sandbox/products", timeout=30)
        if data and isinstance(data, list):
            all_products = data
            print(f"    {len(data)} products found")
            break
        print(f"    Attempt {attempt+1} failed: {err}")
        import time; time.sleep(3)
    if not all_products:
        print("    Could not fetch products after retries")

    # ================================================================
    # STEP 2: Product HTML previews (no auth)
    # ================================================================
    print("\n[2] Downloading product HTML previews...")
    for p in all_products:
        pid = p.get("id")
        name = (p.get("name") or f"P{pid}")[:50]
        preview_url = p.get("preview_url")
        if preview_url:
            html, err = fetch(f"{LIVE_API}{preview_url}")
            if html and isinstance(html, str) and len(html) > 50:
                p["_html_code"] = html
                print(f"    [{pid}] {name[:40]}... ({len(html)} chars)")
            elif html and isinstance(html, dict):
                # JSON response instead of HTML
                p["_preview_data"] = html
        # Also try calling skills
        call_url = p.get("call_url")
        if call_url:
            result, _ = fetch(f"{LIVE_API}{call_url}", method="POST",
                              data={"method": "help", "params": {}, "text": "test", "input": "test"})
            if result:
                p["_call_result"] = result

    # ================================================================
    # STEP 3: Plaza discussions (needs auth - has FULL data)
    # ================================================================
    if token:
        print("\n[3] Plaza discussions (full project data with PRDs)...")
        data, err = fetch(f"{LIVE_API}/plaza/discussions?limit_projects=200", token=token)
        if data and isinstance(data, dict):
            projects_list = data.get("projects", [])
            events_list = data.get("events", [])
            all_events = events_list
            print(f"    {len(projects_list)} projects, {len(events_list)} events")

            for proj in projects_list:
                pid = proj.get("id")
                all_projects[pid] = proj
                progress = proj.get("progress", [])
                prd_count = sum(1 for e in progress if isinstance(e, dict) and e.get("event_type") == "prd_generated")
                msg_count = sum(1 for e in progress if isinstance(e, dict) and e.get("event_type") == "message")
                name = (proj.get("name") or "?")[:45]
                print(f"    [{pid}] {name} | {proj.get('status','?')} | {prd_count} PRDs, {msg_count} msgs")
        else:
            print(f"    Failed: {err}")
            print("    Token may be invalid or expired.")

        # Also get workbench projects (might have extras)
        print("\n[3b] Plaza workbench projects...")
        data2, err2 = fetch(f"{LIVE_API}/plaza/workbench/projects?limit=100", token=token)
        if data2 and isinstance(data2, list):
            for proj in data2:
                pid = proj.get("id")
                if pid not in all_projects:
                    all_projects[pid] = proj
            print(f"    {len(data2)} workbench projects (total unique: {len(all_projects)})")
        else:
            print(f"    Failed: {err2}")

        # Also get agents info
        print("\n[3c] Agents list...")
        agents, err3 = fetch(f"{LIVE_API}/plaza/agents", token=token)
        if agents and isinstance(agents, list):
            print(f"    {len(agents)} agents")
            (batch_dir / "agents.json").write_text(
                json.dumps(agents, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        else:
            print(f"    Failed: {err3}")

        # Dashboard
        print("\n[3d] Dashboard...")
        dash, err4 = fetch(f"{LIVE_API}/transactions/dashboard", token=token)
        if dash and isinstance(dash, dict):
            (batch_dir / "dashboard.json").write_text(
                json.dumps(dash, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            stats = dash.get("stats", {})
            print(f"    Budget: {stats.get('total_budget')}, Earned: {stats.get('total_earned')}, Spent: {stats.get('total_spent')}")
        else:
            print(f"    Failed: {err4}")

        # Transactions
        print("\n[3e] Transactions...")
        txns, err5 = fetch(f"{LIVE_API}/transactions/my?limit=500", token=token)
        if txns and isinstance(txns, list):
            (batch_dir / "transactions.json").write_text(
                json.dumps(txns, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            print(f"    {len(txns)} transactions")

        # Investments
        print("\n[3f] Investments...")
        invs, err6 = fetch(f"{LIVE_API}/transactions/investments/my", token=token)
        if invs and isinstance(invs, list):
            (batch_dir / "investments.json").write_text(
                json.dumps(invs, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            print(f"    {len(invs)} investments")
    else:
        print("\n[3] SKIPPED (no token) - Plaza data requires authentication.")
        print("    To get full data:")
        print("    1. Open browser -> F12 -> Console")
        print("    2. Run: localStorage.getItem('clawthon_token')")
        print("    3. Copy the token and run:")
        print(f'    python download_from_live.py --token "YOUR_TOKEN"')

    # ================================================================
    # STEP 4: Save everything to disk
    # ================================================================
    print(f"\n[4] Saving to {batch_dir}...")

    # --- Products ---
    products_dir = batch_dir / "products"
    products_dir.mkdir(exist_ok=True)
    (products_dir / "_all_products.json").write_text(
        json.dumps(all_products, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for p in all_products:
        pid = p.get("id", 0)
        name = (p.get("name") or f"product_{pid}")
        safe = _safe_name(name)
        pdir = products_dir / f"{pid}_{safe}"
        pdir.mkdir(exist_ok=True)
        (pdir / "info.json").write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")
        if p.get("_html_code"):
            (pdir / "product.html").write_text(p["_html_code"], encoding="utf-8")
        if p.get("_call_result"):
            (pdir / "call_result.json").write_text(
                json.dumps(p["_call_result"], ensure_ascii=False, indent=2), encoding="utf-8"
            )

    # --- Projects (from plaza) ---
    projects_dir = batch_dir / "projects"
    projects_dir.mkdir(exist_ok=True)
    for pid, proj in sorted(all_projects.items()):
        name = proj.get("name") or f"project_{pid}"
        safe = _safe_name(name)
        pdir = projects_dir / f"{pid}_{safe}"
        pdir.mkdir(exist_ok=True)

        # Full JSON
        (pdir / "project.json").write_text(
            json.dumps(proj, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )

        progress = proj.get("progress", [])

        # Extract PRDs
        prd_idx = 0
        disc_lines = [f"# Discussions: {name}\n"]
        has_disc = False
        for evt in progress:
            if not isinstance(evt, dict):
                continue
            et = evt.get("event_type", "")
            content = evt.get("content", "")
            agent = evt.get("agent_name", "")
            ets = evt.get("ts", "")

            if et == "prd_generated" and content:
                prd_idx += 1
                prd_file = pdir / f"PRD_{prd_idx}.md"
                prd_file.write_text(
                    f"# PRD: {name}\n\n"
                    f"- Project ID: {pid}\n"
                    f"- Agent: {agent}\n"
                    f"- Time: {ets}\n\n---\n\n{content}",
                    encoding="utf-8",
                )
            elif et == "message" and content:
                disc_lines.append(f"\n## [{ets}] {agent}\n\n{content}\n")
                has_disc = True
            elif et == "summary" and content:
                (pdir / "summary.md").write_text(
                    f"# Summary: {name}\n\n"
                    f"- Agent: {agent}\n"
                    f"- Time: {ets}\n\n{content}",
                    encoding="utf-8",
                )
            elif et == "product_deployed" and content:
                (pdir / "deploy_log.txt").write_text(
                    f"[{ets}] {agent}: {content}", encoding="utf-8"
                )

        if has_disc:
            (pdir / "discussions.md").write_text("\n".join(disc_lines), encoding="utf-8")

        # Also link product HTML if product ID matches
        for prod in all_products:
            if prod.get("id") == pid and prod.get("_html_code"):
                (pdir / "product.html").write_text(prod["_html_code"], encoding="utf-8")

    # --- Events timeline ---
    if all_events:
        (batch_dir / "all_events.json").write_text(
            json.dumps(all_events, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )

    # --- Index ---
    index = {
        "exported_at": datetime.utcnow().isoformat(),
        "source": LIVE_API,
        "has_auth": bool(token),
        "total_products": len(all_products),
        "total_projects": len(all_projects),
        "total_events": len(all_events),
        "export_dir": str(batch_dir),
    }
    (batch_dir / "INDEX.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- Human-readable summary ---
    summary_lines = [
        f"# Clawthon Data Export",
        f"",
        f"Exported at: {datetime.utcnow().isoformat()}",
        f"Source: {LIVE_API}",
        f"",
        f"## Products ({len(all_products)})",
        "",
    ]
    for p in all_products:
        summary_lines.append(f"- [{p.get('id')}] {p.get('name', '?')[:60]} ({p.get('product_type', '?')})")
    summary_lines.extend(["", f"## Projects ({len(all_projects)})", ""])
    for pid, proj in sorted(all_projects.items()):
        progress = proj.get("progress", [])
        prd_count = sum(1 for e in progress if isinstance(e, dict) and e.get("event_type") == "prd_generated")
        msg_count = sum(1 for e in progress if isinstance(e, dict) and e.get("event_type") == "message")
        summary_lines.append(
            f"- [{pid}] {proj.get('name', '?')[:50]} | {proj.get('status','?')} | {prd_count} PRDs, {msg_count} discussions"
        )
    (batch_dir / "SUMMARY.md").write_text("\n".join(summary_lines), encoding="utf-8")

    print(f"\n{'=' * 65}")
    print(f"  Download complete!")
    print(f"  Products:  {len(all_products)}")
    print(f"  Projects:  {len(all_projects)}")
    print(f"  Events:    {len(all_events)}")
    print(f"  Saved to:  {batch_dir}")
    print(f"{'=' * 65}")

    if not token and not all_projects:
        print(f"\n  NOTE: No project details were downloaded because no token was provided.")
        print(f"  To get FULL data (PRDs, discussions, summaries):")
        print(f"  1. Open https://clawthon-towow.vercel.app in browser")
        print(f"  2. Login with SecondMe")
        print(f"  3. Press F12 -> Console -> type: localStorage.getItem('clawthon_token')")
        print(f"  4. Copy the token value and run:")
        print(f'     python download_from_live.py --token "eyJ..."')


def _safe_name(name: str) -> str:
    bad = '/\\:*?"<>|'
    for ch in bad:
        name = name.replace(ch, "_")
    # Remove problematic chars for Windows paths
    name = name.replace("\uff08", "(").replace("\uff09", ")")
    name = "".join(c if ord(c) < 128 or c in "()_- " else "" for c in name)
    name = name.strip().strip("_").strip()
    if not name:
        name = "unnamed"
    return name[:40]


if __name__ == "__main__":
    main()
