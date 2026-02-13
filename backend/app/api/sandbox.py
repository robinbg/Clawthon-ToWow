"""
Product Sandbox — Agent 真实开发的产品在这里运行

- Web 产品：直接渲染 HTML
- Agent Skill：通过 POST 调用，传入参数，返回结果
- MCP 服务：标准化 JSON-RPC 调用
"""
import json
import logging
import os
import traceback
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from ..models.database import Project, User, get_db
from .auth import get_current_user
from .ai import call_secondme_chat

router = APIRouter(prefix="/sandbox", tags=["Product Sandbox"])
logger = logging.getLogger(__name__)

# ---- Product Registry (survives Vercel cold starts) ----
_PRODUCT_REGISTRY_PATH = Path("/tmp/products_registry.json") if os.environ.get("VERCEL") else Path("products_registry.json")


def _save_product_to_registry(project_id: int, name: str, code: str, product_type: str, description: str = "") -> None:
    try:
        registry: dict = {}
        if _PRODUCT_REGISTRY_PATH.exists():
            registry = json.loads(_PRODUCT_REGISTRY_PATH.read_text())
        registry[str(project_id)] = {
            "name": name,
            "code": code,
            "product_type": product_type,
            "description": description,
        }
        _PRODUCT_REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"Failed to save product registry: {e}")


def _load_product_from_registry(project_id: int) -> Optional[dict]:
    try:
        if not _PRODUCT_REGISTRY_PATH.exists():
            return None
        registry = json.loads(_PRODUCT_REGISTRY_PATH.read_text())
        return registry.get(str(project_id))
    except Exception:
        return None


# ==================== 1. 开发：Agent 生成真实代码 ====================

async def develop_product_code(
    *,
    db: Session,
    project: Project,
    token: str,
) -> dict[str, Any]:
    """
    Code-ReAct: Generate → Verify → Fix → Retry.
    Supports web_app, agent_skill, mcp_service.
    """
    from .ai import parse_json_from_text

    desc = (project.description or project.name or "工具")[:300]
    short_name = (project.name or "Product").replace("[Auto] ", "")[:40]

    # Step 1: Classify product type
    # 分类三种产品：
    # - web_app：面向人类，浏览器使用
    # - agent_skill：面向 Agent 的 Skills Layer（知识与逻辑层）—— "怎么做"
    # - mcp_service：面向 Agent 的 MCP Tool Layer（连接与执行层）—— "能做什么"
    classify_raw = await call_secondme_chat(
        token,
        f"判断项目「{short_name}」（描述：{desc}）应该做成什么类型的产品。\n"
        "三种选择：\n"
        "- web_app：面向人类用户在浏览器中使用的 Web 应用\n"
        "- agent_skill：面向 Agent 的业务技能（知识与逻辑层）—— 定义'怎么做'，包含业务流程编排、领域知识、工作流模板（如 code-review、data-analysis）\n"
        "- mcp_service：面向 Agent 的 MCP 工具服务（连接与执行层）—— 定义'能做什么'，暴露标准化接口、访问外部数据和服务（如 API 网关、数据库连接）\n"
        '只返回 JSON：{"type":"web_app|agent_skill|mcp_service"}',
        enable_web_search=False,
    )
    product_type = "web_app"
    try:
        pt = parse_json_from_text(classify_raw).get("type", "web_app")
        if pt in ("web_app", "mcp_service", "agent_skill"):
            product_type = pt
    except Exception:
        pass

    code = ""
    MAX_REACT_ROUNDS = 2

    # ==================== Web App ====================
    if product_type == "web_app":
        prompt = (
            f"你是前端工程师。为「{short_name}」开发一个完整的单页 HTML 网站。\n"
            f"描述：{desc}\n\n"
            "严格要求：\n"
            "- 输出完整 HTML（内联 CSS+JS），以 <!DOCTYPE html> 开头\n"
            "- 必须包含导航栏、功能区域（卡片/表格/列表）、可交互按钮\n"
            "- 如果核心功能需要后端，用 Mock 假数据代替，并标注黄色横幅'📋 Mock 演示'\n"
            "- 现代设计（白底、蓝色主色、圆角、阴影）、响应式\n"
            "- 底部：Powered by Clawthon AI Agent\n"
            "- 不要引用外部 CDN\n"
            "- 不要输出 Python 代码\n\n"
            "只输出 HTML，不要解释。"
        )
        for attempt in range(MAX_REACT_ROUNDS):
            raw = await call_secondme_chat(token, prompt, enable_web_search=False)
            code = _clean_code(raw, "web_app")
            # Verify: must be valid HTML
            cl = (code or "").lower()
            if code and len(code) > 300 and "<html" in cl and "<body" in cl and "import " not in code[:100].lower():
                break  # ✅ valid
            # Fix: tell AI what went wrong
            prompt = (
                f"你上一次的输出不是有效的 HTML 页面（可能输出了 Python 代码或太短）。\n"
                f"请重新为「{short_name}」生成一个完整的 HTML 网站。\n"
                f"描述：{desc}\n"
                "必须以 <!DOCTYPE html> 开头，包含 <html><head><body> 标签。\n"
                "只输出 HTML 代码，不要 Python，不要解释。"
            )
        # Final fallback
        cl = (code or "").lower()
        if not code or "<html" not in cl or "<body" not in cl:
            code = _generate_fallback_mock_html(short_name, desc, [])

    # ==================== Agent Skill（Claude Skills 官方格式）====================
    # 官方格式：SKILL.md + scripts/ 目录
    # - SKILL.md：Claude 读取的指令文档
    # - scripts/：可执行脚本，Claude 运行并只看 stdout
    # - 通过 skill_id 注册，API 用 container 参数加载
    elif product_type == "agent_skill":
        prompt = f"""为「{short_name}」开发一个 Claude Agent Skill（官方格式）。描述：{desc}

Claude Agent Skills 是文件系统上的目录结构：
```
{short_name}/
├── SKILL.md          # 指令文档（Claude 读取）
├── scripts/
│   ├── main.py       # 核心脚本（Claude 运行，只看 stdout）
│   └── validate.py   # 验证脚本
└── templates/
    └── output.md     # 输出模板
```

请生成一个 JSON，包含这个 Skill 的所有文件内容：

{{
  "skill_id": "英文下划线格式的技能ID",
  "skill_md": "SKILL.md 的完整 Markdown 内容，必须包含：\\n# 技能名称\\n\\n## 概述\\n说明做什么\\n\\n## 使用场景\\n- 场景列表\\n\\n## 工作流程\\n详细步骤\\n\\n## 输入\\n接受什么参数\\n\\n## 输出\\n返回什么结果\\n\\n## 脚本\\n可用的脚本及用途\\n\\n## 示例\\n使用示例\\n\\n## 领域知识\\n关键规则和最佳实践",
  "main_script": "scripts/main.py 的完整 Python 代码（通过 sys.argv 接收输入，print 输出结果，只用标准库，至少 30 行真实逻辑）",
  "validate_script": "scripts/validate.py 的完整 Python 代码（验证输入有效性）",
  "output_template": "templates/output.md 的 Markdown 模板"
}}

只输出 JSON。"""

        raw = await call_secondme_chat(token, prompt, enable_web_search=False)
        skill_data = parse_json_from_text(raw)

        skill_id = skill_data.get("skill_id", "skill")
        skill_md = skill_data.get("skill_md", f"# {short_name}\\n\\n{desc}")
        main_script = skill_data.get("main_script", "import sys\\nprint('Skill executed')")
        validate_script = skill_data.get("validate_script", "print('valid')")
        output_template = skill_data.get("output_template", "# Output\\n\\n{{result}}")

        code = f'''# ================================================================
# Claude Agent Skill: {skill_id}
# 官方格式：SKILL.md + scripts/ + templates/
#
# 目录结构:
#   {skill_id}/
#   ├── SKILL.md
#   ├── scripts/
#   │   ├── main.py
#   │   └── validate.py
#   └── templates/
#       └── output.md
# ================================================================

SKILL_ID = "{skill_id}"

# ============ SKILL.md ============
SKILL_MD = """{skill_md}"""

# ============ scripts/main.py ============
MAIN_SCRIPT = """{main_script}"""

# ============ scripts/validate.py ============
VALIDATE_SCRIPT = """{validate_script}"""

# ============ templates/output.md ============
OUTPUT_TEMPLATE = """{output_template}"""

# ============ 沙盒执行兼容函数 ============
def execute_skill(input_data: dict) -> dict:
    """在沙盒中执行 Skill 的 main.py 脚本"""
    import io, sys
    try:
        text = input_data.get("text", input_data.get("input", str(input_data)))
        old_stdout, old_argv = sys.stdout, sys.argv
        sys.stdout = io.StringIO()
        sys.argv = ["main.py", text]
        exec_ns = {{"__builtins__": __builtins__, "__name__": "__main__"}}
        exec(MAIN_SCRIPT, exec_ns)
        output = sys.stdout.getvalue()
        sys.stdout, sys.argv = old_stdout, old_argv
        return {{"skill": SKILL_ID, "result": output.strip() or "执行完成"}}
    except Exception as e:
        sys.stdout, sys.argv = old_stdout, old_argv
        return {{"skill": SKILL_ID, "error": str(e)}}

# ============ Skill 文件导出（用于下载/部署）============
def export_skill_files() -> dict:
    return {{
        f"{{SKILL_ID}}/SKILL.md": SKILL_MD,
        f"{{SKILL_ID}}/scripts/main.py": MAIN_SCRIPT,
        f"{{SKILL_ID}}/scripts/validate.py": VALIDATE_SCRIPT,
        f"{{SKILL_ID}}/templates/output.md": OUTPUT_TEMPLATE,
    }}
'''
        # Code-ReAct verify
        for attempt in range(MAX_REACT_ROUNDS):
            error = _verify_python_code(code, "execute_skill")
            if not error:
                break
            fix_raw = await call_secondme_chat(token, f"脚本有错误：{error}。请只输出修复后的 main.py Python 脚本代码。项目：{short_name}", enable_web_search=False)
            fixed = _clean_code(fix_raw, "agent_skill")
            if fixed:
                code = code.replace(main_script, fixed)

    # ==================== MCP Server（Anthropic 官方 FastMCP 格式）====================
    # 官方格式：FastMCP SDK，@mcp.tool() 装饰器注册工具
    # 协议：JSON-RPC 2.0，stdio/SSE transport
    # 安装：pip install mcp[cli]
    # 运行：mcp dev server.py 或 python server.py
    else:
        prompt = f"""为「{short_name}」开发一个 MCP Server（Anthropic 官方 FastMCP 格式）。描述：{desc}

官方 FastMCP 格式（pip install mcp[cli]）：

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("server_name")

@mcp.tool()
def my_tool(query: str) -> str:
    \"\"\"工具描述\"\"\"
    return "结果"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

请生成完整代码，包含两部分：
1. 可直接运行的 FastMCP Server（顶部）
2. 不依赖 mcp 包的沙盒兼容版（底部）

```python
# ================================================================
# MCP Server: {short_name}
# 安装: pip install mcp[cli]
# 运行: mcp dev server.py 或 python server.py
# ================================================================

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("{short_name}")

@mcp.tool()
def tool1(param1: str) -> str:
    \"\"\"工具1描述\"\"\"
    # 真实逻辑
    return "结果"

@mcp.tool()
def tool2(data: str, option: str = "default") -> str:
    \"\"\"工具2描述\"\"\"
    return "结果"

@mcp.tool()
def tool3(items: str) -> str:
    \"\"\"工具3描述\"\"\"
    return "结果"

if __name__ == "__main__":
    mcp.run(transport="stdio")

# ================================================================
# 沙盒兼容版（不依赖 mcp 包，可在 Clawthon 沙盒中直接调用）
# ================================================================
# ... 同样的 tool 函数（不需要装饰器）...
# TOOLS = {{"tool1": tool1, ...}}
# def handle_request(method, params): ...
```

要求：
- 至少 3 个 @mcp.tool()，每个有 docstring + 真实逻辑
- 用 Python 类型注解（FastMCP 自动推导 JSON Schema）
- 下方沙盒版只用标准库
- 只输出 Python 代码"""

        for attempt in range(MAX_REACT_ROUNDS):
            raw = await call_secondme_chat(token, prompt, enable_web_search=False)
            code = _clean_code(raw, "mcp_service")
            error = _verify_python_code(code, "handle_request")
            if not error:
                break
            prompt = (
                f"代码有错误：{error}。请修复并重新输出完整 MCP Server 代码。\n"
                f"项目：{short_name}，描述：{desc}。只输出 Python 代码。"
            )

    # Save to project DB
    project.product_code = code
    project.product_type_detail = product_type
    project.product_endpoint = f"/sandbox/product/{project.id}"
    db.commit()
    db.refresh(project)

    # Also persist to registry file (survives Vercel cold starts)
    _save_product_to_registry(
        project.id, project.name or "", code, product_type, project.description or ""
    )

    return {
        "product_type_detail": product_type,
        "code_length": len(code),
        "endpoint": project.product_endpoint,
    }


def _verify_python_code(code: str, expected_func: str) -> Optional[str]:
    """Try to compile and dry-run Python code. Returns error string or None if OK."""
    if not code or len(code) < 20:
        return "代码为空或太短"
    if expected_func not in code:
        return f"代码中未找到函数 {expected_func}"
    try:
        compile(code, "<sandbox>", "exec")
    except SyntaxError as e:
        return f"语法错误: {e}"
    # Try executing to check for import errors etc.
    safe_builtins = {
        "str": str, "int": int, "float": float, "bool": bool,
        "list": list, "dict": dict, "tuple": tuple, "set": set,
        "len": len, "range": range, "enumerate": enumerate,
        "zip": zip, "map": map, "filter": filter,
        "sorted": sorted, "min": min, "max": max, "sum": sum,
        "abs": abs, "round": round, "isinstance": isinstance, "type": type,
        "True": True, "False": False, "None": None,
        "print": lambda *a, **k: None,
        "Exception": Exception, "ValueError": ValueError,
        "TypeError": TypeError, "KeyError": KeyError,
    }
    try:
        ns: dict = {"__builtins__": safe_builtins}
        exec(code, ns)
        if expected_func not in ns:
            return f"执行后未找到函数 {expected_func}"
        # Quick smoke test
        func = ns[expected_func]
        if expected_func == "execute_skill":
            result = func({"test": "hello"})
            if not isinstance(result, dict):
                return f"函数返回类型错误: 期望 dict，得到 {type(result).__name__}"
        elif expected_func == "handle_request":
            result = func("test", {})
            if not isinstance(result, dict):
                return f"函数返回类型错误: 期望 dict，得到 {type(result).__name__}"
    except Exception as e:
        return f"运行时错误: {str(e)[:150]}"
    return None  # ✅ OK


def _generate_fallback_mock_html(name: str, desc: str, mock_features: list) -> str:
    """Generate a simple but valid mock HTML page as fallback."""
    features_html = "".join(f"<li>{f}</li>" for f in (mock_features or [])[:5]) or "<li>核心功能演示</li>"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:system-ui;background:#f0f4f8;min-height:100vh}}
nav{{background:#1e293b;color:#fff;padding:16px 24px;display:flex;justify-content:space-between;align-items:center}}
nav h1{{font-size:18px}}
.container{{max-width:800px;margin:0 auto;padding:24px}}
.banner{{background:#fef3c7;color:#92400e;padding:12px;border-radius:8px;text-align:center;font-size:13px;margin-bottom:20px}}
.card{{background:#fff;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.06);padding:24px;margin-bottom:16px}}
.card h3{{color:#1e293b;margin-bottom:8px}}
.card p{{color:#64748b;font-size:14px;line-height:1.6}}
.btn{{background:#2563eb;color:#fff;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;font-size:14px;margin-top:12px}}
.btn:hover{{background:#1d4ed8}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin:16px 0}}
.stat{{background:#eff6ff;padding:16px;border-radius:8px;text-align:center}}
.stat .num{{font-size:28px;font-weight:700;color:#2563eb}}
.stat .label{{font-size:12px;color:#64748b;margin-top:4px}}
footer{{text-align:center;padding:24px;color:#94a3b8;font-size:12px}}
#result{{display:none;margin-top:12px;padding:16px;background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0}}
</style></head>
<body>
<nav><h1>{name}</h1><span style="font-size:13px">Mock 演示</span></nav>
<div class="container">
<div class="banner">📋 这是 Mock 演示 · 由 AI Agent 自动开发 · 完整功能需要后端支持</div>
<div class="card"><h3>产品介绍</h3><p>{desc}</p></div>
<div class="grid">
<div class="stat"><div class="num">1,234</div><div class="label">活跃用户</div></div>
<div class="stat"><div class="num">98.5%</div><div class="label">满意度</div></div>
<div class="stat"><div class="num">5,678</div><div class="label">处理次数</div></div>
</div>
<div class="card"><h3>核心功能</h3><ul style="margin:8px 0 0 20px;color:#475569;font-size:14px">{features_html}</ul></div>
<div class="card"><h3>试用演示</h3><p>输入内容体验核心流程</p>
<textarea id="inp" style="width:100%;min-height:80px;margin-top:8px;padding:10px;border:1px solid #e2e8f0;border-radius:8px;font-size:14px" placeholder="输入任意内容..."></textarea>
<button class="btn" onclick="document.getElementById('result').style.display='block';document.getElementById('result').innerHTML='<strong>✅ 处理完成</strong><br>输入内容已接收（'+document.getElementById('inp').value.length+'字符），Mock 数据已生成。实际产品将接入后端服务处理。'">开始处理</button>
<div id="result"></div></div>
</div>
<footer>Powered by Clawthon AI Agent · {name}</footer>
</body></html>"""


def _clean_code(raw: str, product_type: str) -> str:
    """Extract clean code from AI response (strip markdown fences etc)."""
    code = raw.strip()
    # Remove markdown code fences
    if code.startswith("```"):
        lines = code.split("\n")
        # Remove first line (```html or ```python)
        lines = lines[1:]
        # Remove last ``` if present
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines)

    if product_type == "web_app":
        # Ensure it starts with DOCTYPE or <html>
        idx = code.lower().find("<!doctype")
        if idx == -1:
            idx = code.lower().find("<html")
        if idx > 0:
            code = code[idx:]
    return code.strip()


# ==================== 2. 预览 Web 产品 ====================

@router.get("/product/{project_id}/preview", response_class=HTMLResponse)
async def preview_web_product(
    project_id: int,
    db: Session = Depends(get_db),
):
    """Serve the agent-built web product as a live HTML page."""
    # Try DB first
    project = db.query(Project).filter(Project.id == project_id).first()
    code = project.product_code if project else None
    product_type = project.product_type_detail if project else None
    name = project.name if project else f"Project #{project_id}"

    # Fallback to registry if DB miss (Vercel cold start)
    if not code:
        reg = _load_product_from_registry(project_id)
        if reg:
            code = reg.get("code")
            product_type = reg.get("product_type")
            name = reg.get("name", name)

    if not code:
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;padding:40px'>"
            f"<h2>🚧 产品尚未开发</h2>"
            f"<p>项目「{name}」还没有生成代码</p>"
            "</body></html>"
        )
    if product_type and product_type != "web_app":
        return HTMLResponse(
            "<html><body style='font-family:sans-serif;text-align:center;padding:40px'>"
            f"<h2>该产品类型为 {product_type}，不支持网页预览</h2>"
            f"<p>请使用 API 调用：POST /sandbox/product/{project_id}/call</p>"
            "</body></html>"
        )
    return HTMLResponse(code)


# ==================== 3. 调用 Agent Skill / MCP 服务 ====================

@router.post("/product/{project_id}/call")
async def call_product(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Call an agent-built skill or MCP service."""
    project = db.query(Project).filter(Project.id == project_id).first()
    code = project.product_code if project else None
    product_type = project.product_type_detail if project else None

    # Fallback to registry
    if not code:
        reg = _load_product_from_registry(project_id)
        if reg:
            code = reg.get("code")
            product_type = reg.get("product_type")

    if not code:
        raise HTTPException(404, "产品不存在或尚未开发")

    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    if product_type == "agent_skill":
        return _execute_skill_sandbox_code(project_id, code, body)
    elif product_type == "mcp_service":
        method = body.get("method", "")
        params = body.get("params", {})
        return _execute_mcp_sandbox_code(project_id, code, method, params)
    else:
        raise HTTPException(400, f"产品类型 {product_type} 不支持 API 调用，请使用 /preview")


_SAFE_BUILTINS: dict[str, Any] = {
    "str": str, "int": int, "float": float, "bool": bool,
    "list": list, "dict": dict, "tuple": tuple, "set": set,
    "len": len, "range": range, "enumerate": enumerate,
    "zip": zip, "map": map, "filter": filter,
    "sorted": sorted, "reversed": reversed,
    "min": min, "max": max, "sum": sum, "abs": abs, "round": round,
    "isinstance": isinstance, "type": type,
    "True": True, "False": False, "None": None,
    "print": lambda *a, **k: None,
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError, "KeyError": KeyError,
}


def _execute_skill_sandbox_code(project_id: int, code: str, input_data: dict) -> JSONResponse:
    try:
        namespace: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS.copy()}
        exec(code, namespace)
        if "execute_skill" not in namespace:
            return JSONResponse({"error": "Skill 代码中未找到 execute_skill 函数"}, status_code=500)
        result = namespace["execute_skill"](input_data)
        return JSONResponse({"success": True, "project_id": project_id, "result": result})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e), "traceback": traceback.format_exc()[-500:]}, status_code=500)


def _execute_mcp_sandbox_code(project_id: int, code: str, method: str, params: dict) -> JSONResponse:
    try:
        namespace: dict[str, Any] = {"__builtins__": _SAFE_BUILTINS.copy()}
        exec(code, namespace)
        if "handle_request" not in namespace:
            return JSONResponse({"error": "MCP 代码中未找到 handle_request 函数"}, status_code=500)
        result = namespace["handle_request"](method, params)
        return JSONResponse({"jsonrpc": "2.0", "result": result, "project_id": project_id})
    except Exception as e:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}}, status_code=500)


# ==================== 4. 列出所有可用产品 ====================

@router.get("/products")
async def list_products(
    db: Session = Depends(get_db),
    product_type: Optional[str] = Query(default=None),
):
    """List all projects that have deployed products (DB + registry fallback)."""
    result = []
    seen_ids: set[int] = set()

    # From DB
    query = db.query(Project).filter(Project.product_code.isnot(None))
    if product_type:
        query = query.filter(Project.product_type_detail == product_type)
    for p in query.order_by(Project.usage_count.desc()).all():
        seen_ids.add(p.id)
        result.append({
            "id": p.id, "name": p.name, "description": p.description,
            "product_type": p.product_type_detail,
            "preview_url": f"/sandbox/product/{p.id}/preview" if p.product_type_detail == "web_app" else None,
            "call_url": f"/sandbox/product/{p.id}/call" if p.product_type_detail in ("agent_skill", "mcp_service") else None,
            "usage_count": p.usage_count or 0,
        })

    # From registry (fill in any missing)
    try:
        if _PRODUCT_REGISTRY_PATH.exists():
            registry = json.loads(_PRODUCT_REGISTRY_PATH.read_text())
            for pid_str, info in registry.items():
                pid = int(pid_str)
                if pid in seen_ids:
                    continue
                pt = info.get("product_type", "")
                if product_type and pt != product_type:
                    continue
                result.append({
                    "id": pid, "name": info.get("name", ""), "description": info.get("description", ""),
                    "product_type": pt,
                    "preview_url": f"/sandbox/product/{pid}/preview" if pt == "web_app" else None,
                    "call_url": f"/sandbox/product/{pid}/call" if pt in ("agent_skill", "mcp_service") else None,
                    "usage_count": 0,
                })
    except Exception:
        pass

    return result
