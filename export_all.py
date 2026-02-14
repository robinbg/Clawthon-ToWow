#!/usr/bin/env python3
"""
Clawthon 全量数据导出脚本
=========================

将所有项目的需求、PRD、讨论记录、产品代码导出到本地磁盘。

用法:
  python export_all.py                          # 从本地后端导出
  python export_all.py --url http://host:8000   # 从指定后端导出
  python export_all.py --db backend/clawthon.db # 直接从数据库导出（无需启动后端）

导出目录: D:\\Clawthon\\exports\\
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def export_via_api(base_url: str, output_dir: Path) -> int:
    """通过 API 导出"""
    import urllib.request

    url = f"{base_url.rstrip('/')}/projects/export/all"
    print(f"📡 从 {url} 获取数据...")

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"❌ API 请求失败: {e}")
        print("   提示: 请确保后端正在运行 (uvicorn server:app --port 8000)")
        return 0

    projects = data.get("projects", [])
    if not projects:
        print("⚠️ 暂无项目数据")
        return 0

    return _save_projects(projects, output_dir)


def export_via_db(db_path: str, output_dir: Path) -> int:
    """直接从 SQLite 数据库导出（无需启动后端）"""
    import sqlite3

    if not os.path.exists(db_path):
        print(f"❌ 数据库文件不存在: {db_path}")
        return 0

    print(f"🗄️ 从数据库 {db_path} 读取...")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM projects ORDER BY created_at ASC")
    rows = cursor.fetchall()

    if not rows:
        print("⚠️ 数据库中暂无项目数据")
        conn.close()
        return 0

    projects = []
    for row in rows:
        row_dict = dict(row)
        prd_content = row_dict.get("prd_content", "")

        # 解析 meta
        meta = {}
        try:
            if prd_content:
                parsed = json.loads(prd_content)
                if isinstance(parsed, dict):
                    meta = parsed
        except Exception:
            pass

        # 从 progress 提取结构化数据
        progress = meta.get("progress", [])
        needs, prds, discussions, summaries, deployments = [], [], [], [], []

        for evt in progress if isinstance(progress, list) else []:
            if not isinstance(evt, dict):
                continue
            et = evt.get("event_type", "")
            content = evt.get("content", "")
            ts = evt.get("ts", "")
            agent = evt.get("agent_name", "")

            if et == "prd_generated":
                prds.append({"timestamp": ts, "agent": agent, "content": content})
            elif et == "message":
                discussions.append({"timestamp": ts, "agent": agent, "content": content})
            elif et == "summary":
                summaries.append({"timestamp": ts, "agent": agent, "content": content})
            elif et == "product_deployed":
                deployments.append({"timestamp": ts, "agent": agent, "content": content})
            elif et == "project_start":
                needs.append({"timestamp": ts, "content": content})

        raw_prd = ""
        if not meta and prd_content:
            raw_prd = prd_content

        projects.append({
            "id": row_dict.get("id"),
            "name": row_dict.get("name"),
            "description": row_dict.get("description"),
            "product_type": row_dict.get("product_type"),
            "status": row_dict.get("status"),
            "valuation": row_dict.get("valuation", 0),
            "total_revenue": row_dict.get("total_revenue", 0),
            "funding_pool": row_dict.get("funding_pool", 0),
            "usage_count": row_dict.get("usage_count", 0),
            "price_per_use": row_dict.get("price_per_use", 0),
            "owner_id": row_dict.get("owner_id"),
            "created_at": row_dict.get("created_at"),
            "updated_at": row_dict.get("updated_at"),
            "topic": meta.get("topic", row_dict.get("description", "")),
            "mode": meta.get("mode", "solo"),
            "source": meta.get("source", "manual"),
            "needs": needs,
            "prds": prds,
            "discussions": discussions,
            "summaries": summaries,
            "deployments": deployments,
            "raw_prd": raw_prd,
            "product_type_detail": row_dict.get("product_type_detail"),
            "product_code": row_dict.get("product_code"),
            "product_endpoint": row_dict.get("product_endpoint"),
            "team_members_raw": row_dict.get("team_members"),
        })

    conn.close()
    return _save_projects(projects, output_dir)


def _save_projects(projects: list, output_dir: Path) -> int:
    """将项目数据保存到磁盘"""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    batch_dir = output_dir / f"batch_{timestamp}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    index_entries = []

    for p in projects:
        pid = p.get("id", 0)
        name = p.get("name", f"project_{pid}")
        safe_name = name.replace("/", "_").replace("\\", "_").replace(":", "_").replace("?", "_").replace('"', "_")[:60]
        proj_dir = batch_dir / f"{pid}_{safe_name}"
        proj_dir.mkdir(parents=True, exist_ok=True)

        # 1) 完整 JSON
        (proj_dir / "project.json").write_text(
            json.dumps(p, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )

        # 2) PRD 文档
        prds = p.get("prds", [])
        for i, prd in enumerate(prds):
            prd_file = proj_dir / f"PRD_{i+1}.md"
            header = f"# PRD: {name}\n\n"
            header += f"- 项目ID: {pid}\n"
            header += f"- 生成时间: {prd.get('timestamp', 'N/A')}\n"
            header += f"- Agent: {prd.get('agent', 'N/A')}\n\n---\n\n"
            prd_file.write_text(header + prd.get("content", ""), encoding="utf-8")

        if p.get("raw_prd"):
            (proj_dir / "PRD_raw.md").write_text(
                f"# PRD: {name}\n\n{p['raw_prd']}", encoding="utf-8"
            )

        # 3) 讨论记录
        discussions = p.get("discussions", [])
        if discussions:
            lines = [f"# 讨论记录: {name}\n"]
            for d in discussions:
                lines.append(f"\n## [{d.get('timestamp', '')}] {d.get('agent', '')}\n")
                lines.append(d.get("content", ""))
            (proj_dir / "discussions.md").write_text("\n".join(lines), encoding="utf-8")

        # 4) 摘要
        summaries = p.get("summaries", [])
        if summaries:
            lines = [f"# 摘要: {name}\n"]
            for s in summaries:
                lines.append(f"\n## [{s.get('timestamp', '')}] {s.get('agent', '')}\n")
                lines.append(s.get("content", ""))
            (proj_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")

        # 5) 产品代码
        code = p.get("product_code")
        if code:
            pt = p.get("product_type_detail", "unknown")
            if pt == "web_app":
                (proj_dir / "product.html").write_text(code, encoding="utf-8")
            elif pt == "agent_skill":
                (proj_dir / "product_skill.py").write_text(code, encoding="utf-8")
            elif pt == "mcp_service":
                (proj_dir / "product_mcp.py").write_text(code, encoding="utf-8")
            else:
                (proj_dir / "product_code.txt").write_text(code, encoding="utf-8")

        saved += 1
        index_entries.append({
            "id": pid,
            "name": name,
            "status": p.get("status"),
            "product_type": p.get("product_type"),
            "prds_count": len(prds),
            "has_raw_prd": bool(p.get("raw_prd")),
            "has_product_code": bool(code),
            "discussions_count": len(discussions),
            "dir": str(proj_dir),
        })
        print(f"  ✅ [{pid}] {name} — {len(prds)} PRDs, {len(discussions)} 讨论, {'有代码' if code else '无代码'}")

    # 写入索引
    index = {
        "exported_at": datetime.utcnow().isoformat(),
        "total_projects": saved,
        "export_dir": str(batch_dir),
        "projects": index_entries,
    }
    (batch_dir / "INDEX.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 写入完整 JSON
    (batch_dir / "all_projects.json").write_text(
        json.dumps({
            "exported_at": datetime.utcnow().isoformat(),
            "total_projects": len(projects),
            "projects": projects,
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    print(f"\n📁 导出目录: {batch_dir}")
    print(f"📊 共导出 {saved} 个项目")
    return saved


def main():
    parser = argparse.ArgumentParser(description="Clawthon 全量数据导出")
    parser.add_argument("--url", default="http://localhost:8000", help="后端 API 地址")
    parser.add_argument("--db", default="", help="直接从数据库文件导出（跳过 API）")
    parser.add_argument("--output", default="D:/Clawthon/exports", help="导出目录")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("🦞 Clawthon 全量数据导出")
    print("=" * 60)

    if args.db:
        count = export_via_db(args.db, output_dir)
    else:
        count = export_via_api(args.url, output_dir)

    if count == 0:
        print("\n💡 尝试直接从数据库导出:")
        # 自动查找数据库文件
        for db_candidate in [
            "backend/clawthon.db",
            "clawthon.db",
            "D:/Clawthon/backend/clawthon.db",
        ]:
            if os.path.exists(db_candidate):
                print(f"   找到数据库: {db_candidate}")
                count = export_via_db(db_candidate, output_dir)
                break
        else:
            print("   未找到数据库文件")

    print(f"\n🎯 导出完成: {count} 个项目")


if __name__ == "__main__":
    main()
