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
    """Let Agent write real code for the project. Returns {product_type_detail, code, description}."""

    # Decide what kind of product to build based on project description
    # All products are web_app — the platform can only serve web applications
    product_type = "web_app"

    desc = (project.description or project.name or "工具")[:300]
    short_name = (project.name or "Product").replace("[Auto] ", "")[:40]

    # Step 1: Let Agent assess feasibility — can this be fully implemented in pure client-side JS?
    assess_prompt = f"""判断项目「{short_name}」能否用纯前端 JavaScript（无后端、无数据库、无 API 调用）完全实现核心功能。
描述：{desc}

只返回 JSON：
{{"feasible": true或false, "reason": "一句话理由", "mock_features": ["如果不能完全实现，列出需要mock的功能"]}}"""

    from .ai import parse_json_from_text
    assess_raw = await call_secondme_chat(token, assess_prompt, enable_web_search=False)
    assess = parse_json_from_text(assess_raw)
    is_feasible = assess.get("feasible", False)
    mock_features = assess.get("mock_features", [])

    if product_type == "web_app" and is_feasible:
        # FULL implementation — ask for real JS logic
        logic_prompt = f"""项目「{short_name}」可以用纯前端实现。描述：{desc}

请返回 JSON（不要其他内容）：
{{
  "title": "产品名称（10字以内）",
  "subtitle": "一句话描述（20字以内）",
  "input_label": "输入框的提示文字",
  "input_placeholder": "输入框 placeholder",
  "button_text": "按钮文字（如：分析、生成、计算）",
  "features": ["功能1名称", "功能2名称", "功能3名称"],
  "js_process_function": "processInput(text)函数体，接收用户输入text，返回HTML结果字符串。必须有真实逻辑（字符串处理/计算/转换/分析），不少于15行JS代码。不能用fetch/XMLHttpRequest。"
}}"""
        logic_raw = await call_secondme_chat(token, logic_prompt, enable_web_search=False)
        logic = parse_json_from_text(logic_raw)

    elif product_type == "web_app":
        # MOCK mode — Let SecondMe write a COMPLETE custom HTML page from scratch based on PRD
        # No template — every product looks different
        mock_prompt = f"""你是一个资深前端开发工程师。请根据以下产品需求，从零开发一个完整的 Mock 演示网站。

产品名称：{short_name}
产品描述：{desc}
需要后端才能实现的功能（用 Mock 数据代替）：{', '.join(mock_features) if mock_features else '需要服务端支持的功能'}

## 要求：
1. 输出一个完整的 HTML 文件，包含内联 CSS 和 JS
2. 这是一个 Mock 演示站——界面和交互流程要完整，但数据用预设的假数据
3. 页面必须像一个真实产品的首页/主界面，包含：
   - 顶部导航栏（产品名+几个菜单项）
   - 产品 Hero 区域或核心功能展示
   - 至少 2-3 个功能区域（用卡片/表格/列表展示 Mock 数据）
   - 可交互元素（按钮点击弹出 mock 结果、Tab 切换、搜索过滤等）
   - 底部信息栏
4. 在页面某处用黄色横幅标注"📋 这是 Mock 演示 · 由 AI Agent 自动开发 · 完整功能需要后端支持"
5. 底部显示 "Powered by Clawthon AI Agent"
6. 设计要专业、现代（白色/浅灰底、蓝色主色调、圆角卡片、阴影）
7. 不要引用外部 CDN，CSS/JS 全部内联
8. 必须以 <!DOCTYPE html> 开头

每个产品的页面布局和功能区域都应该不同——根据产品需求定制设计，不要用通用模板。

只输出 HTML 代码，不要任何解释。"""

        code = await call_secondme_chat(token, mock_prompt, enable_web_search=False)
        code = _clean_code(code, "web_app")

        # If SecondMe returned garbage, use a minimal fallback
        if not code or len(code) < 200 or not code.strip().lower().startswith("<!doctype"):
            code = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{short_name}</title></head>
<body style="font-family:system-ui;max-width:700px;margin:40px auto;padding:20px">
<h1>{short_name}</h1><p>{desc}</p>
<div style="background:#fef3c7;padding:12px;border-radius:8px;margin:20px 0">📋 Mock 演示 · 由 AI Agent 开发</div>
<p>产品开发中...</p>
<footer style="margin-top:40px;color:#94a3b8;font-size:12px">Powered by Clawthon AI Agent</footer>
</body></html>"""

    # For feasible products, use the template approach
    if is_feasible:
        logic = parse_json_from_text(logic_raw) if 'logic_raw' in dir() else {}
        title = logic.get("title", short_name)
        subtitle = logic.get("subtitle", desc[:50])
        input_label = logic.get("input_label", "请输入内容")
        placeholder = logic.get("input_placeholder", "在此输入...")
        btn_text = logic.get("button_text", "处理")
        features = logic.get("features", ["功能1", "功能2", "功能3"])
        features_html = "".join(f'<span style="background:#eff6ff;color:#2563eb;padding:4px 12px;border-radius:20px;font-size:13px">{f}</span>' for f in features[:5])
        js_body = logic.get("js_process_function", "return '<p>处理完成：' + text.length + ' 个字符</p>';")

        code = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:system-ui,-apple-system,sans-serif;background:#f0f4f8;min-height:100vh;padding:20px}}
.container{{max-width:700px;margin:0 auto}}
.header{{text-align:center;padding:30px 0}}
.header h1{{font-size:28px;color:#1e293b;margin-bottom:8px}}
.header p{{color:#64748b;font-size:15px}}
.features{{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin-top:16px}}
.card{{background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.08);padding:28px;margin-top:20px}}
.card label{{display:block;font-weight:600;color:#334155;margin-bottom:10px;font-size:15px}}
.card textarea{{width:100%;min-height:120px;border:2px solid #e2e8f0;border-radius:12px;padding:14px;font-size:15px;resize:vertical;outline:none;transition:border .2s}}
.card textarea:focus{{border-color:#2563eb}}
.btn{{display:block;width:100%;padding:14px;background:#2563eb;color:#fff;border:none;border-radius:12px;font-size:16px;font-weight:600;cursor:pointer;margin-top:16px;transition:background .2s}}
.btn:hover{{background:#1d4ed8}}
.result{{margin-top:20px;padding:20px;background:#f8fafc;border-radius:12px;border:1px solid #e2e8f0;min-height:80px;font-size:14px;line-height:1.7;color:#334155}}
.result:empty{{display:none}}
.footer{{text-align:center;padding:24px 0;color:#94a3b8;font-size:12px}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{title}</h1>
    <p>{subtitle}</p>
    <div class="features">{features_html}</div>
  </div>
  <div class="card">
    <label>{input_label}</label>
    <textarea id="input" placeholder="{placeholder}"></textarea>
    <button class="btn" onclick="run()">{btn_text}</button>
  </div>
  <div class="card" id="resultCard" style="display:none">
    <label>处理结果</label>
    <div class="result" id="result"></div>
  </div>
  <div class="footer">Powered by Clawthon AI Agent · {short_name}</div>
</div>
<script>
function processInput(text) {{
  try {{
    {js_body}
  }} catch(e) {{
    return '<p style="color:red">处理出错：' + e.message + '</p>';
  }}
}}
function run() {{
  var text = document.getElementById('input').value.trim();
  if(!text) {{ alert('请先输入内容'); return; }}
  document.getElementById('resultCard').style.display = 'block';
  document.getElementById('result').innerHTML = '<div style="text-align:center;color:#2563eb;padding:20px">⏳ 处理中...</div>';
  setTimeout(function() {{ document.getElementById('result').innerHTML = processInput(text); }}, 300);
}}
</script>
</body>
</html>"""

    elif product_type == "agent_skill":
        code_prompt = f"""为项目「{short_name}」写一个 Python 函数。描述：{desc}

要求：函数名 execute_skill，签名 def execute_skill(input_data: dict) -> dict
必须有真实处理逻辑（不是echo），只用标准库，包含错误处理。
只输出 Python 代码。"""
        code = await call_secondme_chat(token, code_prompt, enable_web_search=False)
        code = _clean_code(code, "agent_skill")

    else:  # mcp_service
        code_prompt = f"""为项目「{short_name}」写一个 MCP 服务 Python 函数。描述：{desc}

要求：函数名 handle_request，签名 def handle_request(method: str, params: dict) -> dict
支持至少3个method，真实逻辑，只用标准库。
只输出 Python 代码。"""
        code = await call_secondme_chat(token, code_prompt, enable_web_search=False)
        code = _clean_code(code, "mcp_service")

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
