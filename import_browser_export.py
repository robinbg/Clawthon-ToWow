#!/usr/bin/env python3
"""
将浏览器导出的 JSON 文件解析为本地结构化文件。

用法:
  python import_browser_export.py <json文件路径>

示例:
  python import_browser_export.py exports/clawthon_full_export_2026-02-13T15-20-00.json
  python import_browser_export.py "C:/Users/admin/Downloads/clawthon_full_export_2026-02-13T15-20-00.json"
"""
import json
import sys
import os
from datetime import datetime
from pathlib import Path


def safe_name(name):
    for ch in '/\\:*?"<>|':
        name = name.replace(ch, '_')
    return name.strip()[:50]


def main():
    if len(sys.argv) < 2:
        # Auto-detect: find the newest clawthon_full_export*.json in Downloads or exports/
        candidates = []
        for d in [
            Path.home() / "Downloads",
            Path("D:/Clawthon/exports"),
            Path("exports"),
            Path("."),
        ]:
            if d.exists():
                for f in d.glob("clawthon_full_export*.json"):
                    candidates.append(f)
        if candidates:
            candidates.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            json_file = candidates[0]
            print(f"Auto-detected: {json_file}")
        else:
            print("Usage: python import_browser_export.py <json_file>")
            print("No clawthon_full_export*.json found in Downloads or exports/")
            sys.exit(1)
    else:
        json_file = Path(sys.argv[1])

    if not json_file.exists():
        print(f"File not found: {json_file}")
        sys.exit(1)

    print(f"Loading {json_file} ({json_file.stat().st_size / 1024:.1f} KB)...")
    data = json.loads(json_file.read_text(encoding="utf-8"))

    projects = data.get("projects", [])
    products = data.get("products", [])
    events = data.get("events", [])
    agents = data.get("agents", [])
    dashboard = data.get("dashboard")
    transactions = data.get("transactions", [])
    investments = data.get("investments", [])

    print(f"\n{'='*60}")
    print(f"  Projects:     {len(projects)}")
    print(f"  Products:     {len(products)}")
    print(f"  Events:       {len(events)}")
    print(f"  Agents:       {len(agents)}")
    print(f"  Transactions: {len(transactions)}")
    print(f"  Investments:  {len(investments)}")
    print(f"{'='*60}\n")

    out_dir = Path("D:/Clawthon/exports/browser_export")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save raw JSON
    (out_dir / "raw_export.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    # ---- Projects ----
    proj_dir = out_dir / "projects"
    proj_dir.mkdir(exist_ok=True)

    total_prds = 0
    total_discussions = 0
    total_summaries = 0
    total_deploys = 0

    for proj in sorted(projects, key=lambda x: x.get("id", 0)):
        pid = proj.get("id", 0)
        name = proj.get("name", f"project_{pid}")
        sname = safe_name(name)
        pdir = proj_dir / f"{pid}_{sname}"
        pdir.mkdir(exist_ok=True)

        # Full JSON
        (pdir / "project.json").write_text(
            json.dumps(proj, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )

        progress = proj.get("progress", [])
        prd_idx = 0
        disc_lines = []
        summary_lines = []

        for evt in (progress if isinstance(progress, list) else []):
            if not isinstance(evt, dict):
                continue
            et = evt.get("event_type", "")
            content = evt.get("content", "")
            agent = evt.get("agent_name", "")
            ts = evt.get("ts", "")

            if et == "prd_generated" and content:
                prd_idx += 1
                total_prds += 1
                (pdir / f"PRD_{prd_idx}.md").write_text(
                    f"# PRD: {name}\n\n"
                    f"- Project ID: {pid}\n"
                    f"- Agent: {agent}\n"
                    f"- Time: {ts}\n\n---\n\n{content}",
                    encoding="utf-8",
                )

            elif et == "message" and content:
                total_discussions += 1
                disc_lines.append(f"\n## [{ts}] {agent}\n\n{content}\n")

            elif et == "summary" and content:
                total_summaries += 1
                summary_lines.append(f"\n## [{ts}] {agent}\n\n{content}\n")

            elif et == "product_deployed" and content:
                total_deploys += 1
                (pdir / "deploy_log.txt").write_text(
                    f"[{ts}] {agent}: {content}", encoding="utf-8"
                )

        if disc_lines:
            (pdir / "discussions.md").write_text(
                f"# Discussions: {name}\n" + "\n".join(disc_lines), encoding="utf-8"
            )

        if summary_lines:
            (pdir / "summary.md").write_text(
                f"# Summary: {name}\n" + "\n".join(summary_lines), encoding="utf-8"
            )

        # Link product HTML
        for prod in products:
            if prod.get("id") == pid and prod.get("_html_code"):
                (pdir / "product.html").write_text(prod["_html_code"], encoding="utf-8")

        status = proj.get("status", "?")
        print(f"  [{pid:>3}] {status:<14} {prd_idx} PRDs  {len(disc_lines)} msgs  {name[:50]}")

    # ---- Products ----
    prod_dir = out_dir / "products"
    prod_dir.mkdir(exist_ok=True)

    (prod_dir / "_all_products.json").write_text(
        json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for p in products:
        pid = p.get("id", 0)
        pname = safe_name(p.get("name", f"product_{pid}"))
        ppdir = prod_dir / f"{pid}_{pname}"
        ppdir.mkdir(exist_ok=True)
        info = {k: v for k, v in p.items() if k != "_html_code"}
        (ppdir / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        if p.get("_html_code"):
            (ppdir / "product.html").write_text(p["_html_code"], encoding="utf-8")

    # ---- Other data ----
    if agents:
        (out_dir / "agents.json").write_text(
            json.dumps(agents, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if events:
        (out_dir / "all_events.json").write_text(
            json.dumps(events, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
    if dashboard:
        (out_dir / "dashboard.json").write_text(
            json.dumps(dashboard, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
    if transactions:
        (out_dir / "transactions.json").write_text(
            json.dumps(transactions, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
    if investments:
        (out_dir / "investments.json").write_text(
            json.dumps(investments, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )

    # ---- Index + Summary ----
    (out_dir / "INDEX.json").write_text(json.dumps({
        "exported_at": data.get("exported_at", datetime.utcnow().isoformat()),
        "source": data.get("source", "browser"),
        "total_projects": len(projects),
        "total_products": len(products),
        "total_events": len(events),
        "total_prds": total_prds,
        "total_discussions": total_discussions,
        "total_summaries": total_summaries,
        "total_deploys": total_deploys,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Clawthon Browser Export",
        f"",
        f"Exported at: {data.get('exported_at', 'N/A')}",
        f"Source: {data.get('source', 'browser')}",
        f"",
        f"## Stats",
        f"- Projects: {len(projects)}",
        f"- Products: {len(products)}",
        f"- PRDs: {total_prds}",
        f"- Discussions: {total_discussions}",
        f"- Summaries: {total_summaries}",
        f"- Product Deploys: {total_deploys}",
        f"",
        f"## Projects ({len(projects)})",
        f"",
    ]
    for p in sorted(projects, key=lambda x: x.get("id", 0)):
        pid = p.get("id", 0)
        progress = p.get("progress", [])
        prds = sum(1 for e in progress if isinstance(e, dict) and e.get("event_type") == "prd_generated")
        msgs = sum(1 for e in progress if isinstance(e, dict) and e.get("event_type") == "message")
        lines.append(f"- [{pid}] {p.get('name', '?')[:60]} | {p.get('status', '?')} | {prds} PRDs, {msgs} msgs")

    lines.extend(["", f"## Products ({len(products)})", ""])
    for p in products:
        lines.append(f"- [{p.get('id')}] {p.get('name', '?')[:60]} ({p.get('product_type', '?')})")

    (out_dir / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"  Import complete!")
    print(f"  Projects:    {len(projects)}")
    print(f"  PRDs:        {total_prds}")
    print(f"  Discussions: {total_discussions}")
    print(f"  Summaries:   {total_summaries}")
    print(f"  Products:    {len(products)} ({sum(1 for p in products if p.get('_html_code'))} with HTML)")
    print(f"  Deploys:     {total_deploys}")
    print(f"  Saved to:    {out_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
