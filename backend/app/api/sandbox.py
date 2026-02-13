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
    classify_raw = await call_secondme_chat(
        token,
        f"判断项目「{short_name}」（描述：{desc}）最适合做哪种产品。"
        "如果面向人类用户用浏览器使用，返回 web_app；"
        "如果是给其他 Agent 调用的能力接口，返回 agent_skill；"
        "如果是标准化数据/工具 API 服务，返回 mcp_service。"
        '只返回 JSON：{"type":"web_app|agent_skill|mcp_service"}',
        enable_web_search=False,
    )
    product_type = "web_app"
    try:
        pt = parse_json_from_text(classify_raw).get("type", "web_app")
        if pt in ("web_app", "agent_skill", "mcp_service"):
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

    # ==================== Agent Skill (MCP Tool 格式 — Anthropic 标准) ====================
    # Skills = 单个 MCP Tool，这样 Agent 之间可以用统一协议互相调用
    elif product_type == "agent_skill":
        prompt = f"""为「{short_name}」开发一个 Agent Skill（遵循 Anthropic MCP Tool 格式）。描述：{desc}

一个 Skill 就是一个 MCP Tool。请生成完整 Python 模块：

```python
# === Skill 定义（MCP Tool 格式）===
SKILL_NAME = "skill_name"
SKILL_DESCRIPTION = "这个 Skill 做什么"
SKILL_INPUT_SCHEMA = {{
    "type": "object",
    "properties": {{
        "text": {{"type": "string", "description": "输入文本"}},
        # ... 更多参数
    }},
    "required": ["text"]
}}

def _execute_impl(arguments: dict) -> dict:
    \"\"\"Skill 核心逻辑（纯函数，不依赖外部包）\"\"\"
    text = arguments.get("text", "")
    # ... 真实处理逻辑 ...
    return {{
        "type": "text",
        "text": "处理结果",
        "metadata": {{}}  # 可选的元数据
    }}

# === 沙盒兼容函数 ===
def execute_skill(input_data: dict) -> dict:
    return _execute_impl(input_data)

# === MCP Tool 注册信息（供 MCP Server 使用）===
MCP_TOOL = {{
    "name": SKILL_NAME,
    "description": SKILL_DESCRIPTION,
    "inputSchema": SKILL_INPUT_SCHEMA
}}
```

要求：
- _execute_impl 必须有真实处理逻辑（不是 echo），至少 15 行
- 只用 Python 标准库
- 包含 try/except 错误处理
- inputSchema 遵循 JSON Schema
- 只输出 Python 代码"""

        for attempt in range(MAX_REACT_ROUNDS):
            raw = await call_secondme_chat(token, prompt, enable_web_search=False)
            code = _clean_code(raw, "agent_skill")
            error = _verify_python_code(code, "execute_skill")
            if not error:
                break
            prompt = (
                f"你上次生成的代码有错误：{error}\n"
                f"请修复并重新输出完整代码（包含 Skill 类和 execute_skill 兼容函数）。\n"
                f"项目：{short_name}，描述：{desc}\n"
                "只输出 Python 代码。"
            )

    # ==================== MCP Service (Anthropic 官方 MCP Python SDK 格式) ====================
    else:
        prompt = f"""为「{short_name}」开发一个 MCP (Model Context Protocol) Server。描述：{desc}

请按照 Anthropic 官方 MCP Python SDK 格式生成代码，包含：

1. 标准 MCP Server 定义（使用 mcp.server.Server 和装饰器）
2. list_tools() 返回 Tool 列表，每个 Tool 有 name/description/inputSchema
3. call_tool(name, arguments) 处理工具调用
4. 同时提供一个 handle_request(method, params) -> dict 兼容函数（用于沙盒测试）

示例结构：
```python
# === MCP Server 定义（Anthropic 官方格式）===
# 需要 pip install mcp

# from mcp.server import Server
# from mcp.types import Tool, TextContent

SERVER_NAME = "service_name"
TOOLS = [
    {{
        "name": "tool1",
        "description": "工具1描述",
        "inputSchema": {{
            "type": "object",
            "properties": {{
                "query": {{"type": "string", "description": "查询内容"}}
            }},
            "required": ["query"]
        }}
    }},
    {{
        "name": "tool2",
        "description": "工具2描述",
        "inputSchema": {{
            "type": "object",
            "properties": {{
                "data": {{"type": "string"}}
            }}
        }}
    }}
]

def _call_tool_impl(name: str, arguments: dict) -> dict:
    \"\"\"工具调用的核心实现（纯函数，不依赖 mcp 包）\"\"\"
    if name == "tool1":
        query = arguments.get("query", "")
        # ... 真实处理逻辑 ...
        return {{"type": "text", "text": "处理结果"}}
    elif name == "tool2":
        # ...
        return {{"type": "text", "text": "结果"}}
    return {{"type": "error", "text": f"Unknown tool: {{name}}"}}

# === 沙盒兼容函数 ===
def handle_request(method: str, params: dict) -> dict:
    \"\"\"兼容沙盒调用：method=tool名，params=arguments\"\"\"
    return _call_tool_impl(method, params)

# === 完整 MCP Server 启动代码（需要 mcp 包）===
# def create_server():
#     server = Server(SERVER_NAME)
#     @server.list_tools()
#     async def list_tools():
#         from mcp.types import Tool
#         return [Tool(**t) for t in TOOLS]
#     @server.call_tool()
#     async def call_tool(name: str, arguments: dict):
#         from mcp.types import TextContent
#         result = _call_tool_impl(name, arguments)
#         return [TextContent(type="text", text=result.get("text", str(result)))]
#     return server
```

要求：
- 至少3个 tools，每个有真实处理逻辑
- _call_tool_impl 只用标准库
- inputSchema 遵循 JSON Schema 格式
- 包含错误处理
- 只输出 Python 代码"""

        for attempt in range(MAX_REACT_ROUNDS):
            raw = await call_secondme_chat(token, prompt, enable_web_search=False)
            code = _clean_code(raw, "mcp_service")
            error = _verify_python_code(code, "handle_request")
            if not error:
                break
            prompt = (
                f"你上次生成的代码有错误：{error}\n"
                f"请修复并重新输出完整代码（包含 MCP 类和 handle_request 兼容函数）。\n"
                f"项目：{short_name}，描述：{desc}\n"
                "只输出 Python 代码。"
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
