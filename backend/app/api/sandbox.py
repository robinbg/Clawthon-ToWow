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
    classify_prompt = (
        f"项目名称：{project.name}\n"
        f"项目描述：{project.description or ''}\n\n"
        "请判断这个项目最适合做成什么类型的产品，只返回 JSON：\n"
        '{"type": "web_app|agent_skill|mcp_service", "reason": "一句话理由"}'
    )
    classify_raw = await call_secondme_chat(token, classify_prompt, enable_web_search=False)
    product_type = "web_app"  # default
    try:
        from .ai import parse_json_from_text
        parsed = parse_json_from_text(classify_raw)
        pt = parsed.get("type", "web_app")
        if pt in ("web_app", "agent_skill", "mcp_service"):
            product_type = pt
    except Exception:
        pass

    # Generate actual code
    if product_type == "web_app":
        code_prompt = (
            f"你是一个全栈开发 Agent。请为项目「{project.name}」开发一个完整的单页 Web 应用。\n"
            f"项目描述：{project.description}\n\n"
            "要求：\n"
            "1. 输出一个完整的 HTML 文件（包含 CSS 和 JS，全部内联）\n"
            "2. 界面美观，使用现代设计（圆角、渐变、阴影）\n"
            "3. 必须有真实的交互功能（不是静态页面）\n"
            "4. 顶部显示产品名称和简介\n"
            "5. 底部显示 'Powered by Clawthon AI Agent'\n"
            "6. 响应式设计，手机也能用\n\n"
            "只输出 HTML 代码，不要任何解释。以 <!DOCTYPE html> 开头。"
        )
    elif product_type == "agent_skill":
        code_prompt = (
            f"你是一个 Agent 技能开发者。请为项目「{project.name}」开发一个 Agent Skill。\n"
            f"项目描述：{project.description}\n\n"
            "要求：\n"
            "1. 输出一个 Python 函数，函数名为 `execute_skill`\n"
            "2. 函数签名：`def execute_skill(input_data: dict) -> dict`\n"
            "3. input_data 包含用户传入的参数\n"
            "4. 返回值是一个 dict，包含处理结果\n"
            "5. 函数内不要使用任何外部库（只用标准库）\n"
            "6. 在函数开头加注释说明输入输出格式\n"
            "7. 包含错误处理\n\n"
            "只输出 Python 代码，不要解释。"
        )
    else:  # mcp_service
        code_prompt = (
            f"你是一个 MCP 服务开发者。请为项目「{project.name}」开发一个 MCP 兼容服务。\n"
            f"项目描述：{project.description}\n\n"
            "要求：\n"
            "1. 输出一个 Python 函数，函数名为 `handle_request`\n"
            "2. 函数签名：`def handle_request(method: str, params: dict) -> dict`\n"
            "3. 支持至少 2 个 method\n"
            "4. 返回 JSON-RPC 格式的响应\n"
            "5. 函数内不要使用任何外部库\n"
            "6. 包含错误处理\n\n"
            "只输出 Python 代码，不要解释。"
        )

    code = await call_secondme_chat(token, code_prompt, enable_web_search=False)
    code = _clean_code(code, product_type)

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
