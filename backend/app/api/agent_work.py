"""
Agent 自主工作流 — 发现需求、生成PRD、开发MVP
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List

from ..models.database import get_db, User, Project, ProjectStatus, ProductType
from ..services.project_service import ProjectService
from ..core.config import get_settings
from .auth import get_current_user
from .ai import call_agent_chat, parse_json_from_text

import httpx

router = APIRouter(prefix="/agent", tags=["Agent自主工作"])
logger = logging.getLogger(__name__)
settings = get_settings()


# ==================== 数据模型 ====================

class NeedDiscovery(BaseModel):
    """发现的需求/痛点"""
    title: str
    pain_point: str
    target_users: str  # "human" | "agent" | "both"
    product_type: str
    market_size: str
    confidence: str  # "high" | "medium" | "low"


class DiscoverResponse(BaseModel):
    analysis: str
    needs: List[NeedDiscovery]


class GeneratePRDRequest(BaseModel):
    project_id: int


class PRDContent(BaseModel):
    overview: str
    target_users: str
    core_features: List[str]
    tech_stack: str
    mvp_scope: str
    success_metrics: str
    full_prd: str


class DevelopMVPRequest(BaseModel):
    project_id: int


class MVPCode(BaseModel):
    html: str
    description: str
    features: List[str]


class CreateFromNeedRequest(BaseModel):
    title: str
    description: str
    product_type: str


# ==================== Step 1: 发现需求 ====================

@router.post("/discover-needs")
async def discover_needs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Agent 自主发现需求 — 通过 OpenClaw Gateway 流式调用（避免 Vercel 超时）"""

    all_projects = ProjectService.get_all_projects(db)
    existing = [f"- {p.name}: {p.description}" for p in all_projects[:10]]
    existing_text = "\n".join(existing) if existing else "（暂无）"

    prompt = f"""请搜索互联网，了解当前AI应用和工具的最新趋势，然后发现3个真实可行的产品需求。

平台背景：Clawthon是一个AI自治经济平台，Agent可以开发面向人类的Web工具或面向其他Agent的API服务。
已有产品：{existing_text}

请直接用JSON格式回复：
{{"analysis":"调研发现","needs":[{{"title":"名称","pain_point":"痛点","target_users":"human或agent或both","product_type":"agent_skill或agent_mcp或agent_service或human_web","market_size":"规模","confidence":"high或medium或low"}}]}}"""

    from ..core.openclaw import chat_stream as openclaw_stream, chat as openclaw_chat

    # 流式代理：通过 OpenClaw Gateway 调用 Agent
    async def stream_discover():
        full_text = ""
        try:
            async for chunk in openclaw_stream(
                prompt,
                session_id=f"clawthon-discover-{current_user.id}",
                enable_web_search=True,
                agent_token=current_user.access_token or "",
            ):
                # 从 SSE 事件中提取进度
                if "data:" in chunk:
                    try:
                        data_str = chunk.split("data:", 1)[1].strip()
                        data = json.loads(data_str)
                        if data.get("type") == "text":
                            content = data.get("content", "")
                            full_text += content
                            yield f"data: {json.dumps({'type':'progress','content':content})}\n\n"
                        elif data.get("type") == "error":
                            yield chunk
                            return
                        elif data.get("type") == "done":
                            break
                    except (json.JSONDecodeError, IndexError):
                        continue

        except Exception as e:
            yield f"data: {json.dumps({'type':'error','content':str(e)[:200]})}\n\n"
            return

        # 解析 JSON
        if full_text:
            parsed = parse_json_from_text(full_text)
            if parsed.get("needs"):
                yield f"data: {json.dumps({'type':'result','data':parsed}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type':'raw','content':full_text[:1500]}, ensure_ascii=False)}\n\n"
        else:
            yield f"data: {json.dumps({'type':'error','content':'Agent 未返回内容'})}\n\n"

        yield f"data: {json.dumps({'type':'done'})}\n\n"

    return StreamingResponse(
        stream_discover(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ==================== Step 1.5: 从需求创建项目 ====================

@router.post("/create-from-need")
async def create_project_from_need(
    req: CreateFromNeedRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """从发现的需求创建项目"""
    from ..schemas.schemas import ProjectCreate

    product_type_map = {
        "agent_skill": ProductType.AGENT_SKILL,
        "agent_mcp": ProductType.AGENT_MCP,
        "agent_service": ProductType.AGENT_SERVICE,
        "human_web": ProductType.HUMAN_WEB,
        "human_app": ProductType.HUMAN_APP,
    }

    data = ProjectCreate(
        name=req.title,
        description=req.description,
        product_type=product_type_map.get(req.product_type, ProductType.AGENT_SKILL).value,
    )

    project = ProjectService.create_project(db, current_user.id, data)
    return {"id": project.id, "name": project.name, "status": project.status.value}


# ==================== Step 2: 生成 PRD ====================

@router.post("/generate-prd", response_model=PRDContent)
async def generate_prd(
    req: GeneratePRDRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Agent 为项目自动生成 PRD"""
    project = ProjectService.get_project_by_id(db, req.project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if project.owner_id != current_user.id:
        raise HTTPException(403, "无权操作此项目")

    prompt = f"""你是一个 AI 产品经理 Agent。请为以下项目生成一份精炼的 PRD（产品需求文档）。

项目信息：
- 名称：{project.name}
- 描述：{project.description}
- 产品类型：{project.product_type.value if project.product_type else '未知'}

要求：
- PRD 应聚焦 MVP（最小可行产品）
- 如果是面向 Agent 的产品，需要定义输入/输出接口
- 如果是面向人类的产品，需要描述用户界面

用 JSON 格式回复：
{{
  "overview": "产品概述（50字以内）",
  "target_users": "目标用户描述（30字以内）",
  "core_features": ["核心功能1", "核心功能2", "核心功能3"],
  "tech_stack": "技术方案（30字以内）",
  "mvp_scope": "MVP范围（50字以内）",
  "success_metrics": "成功标准（30字以内）",
  "full_prd": "完整的PRD文档内容（200字以内，用markdown格式）"
}}"""

    # 联网搜索竞品
    try:
        competitor_info = await call_agent_chat(
            current_user.access_token or "",
            f"请搜索互联网，找到与「{project.name} - {project.description}」类似的现有产品或服务，分析优缺点。",
            enable_web_search=True,
        )
        if competitor_info:
            prompt += f"\n\n## 竞品调研\n{competitor_info[:500]}"
    except Exception as e:
        logger.warning(f"Competitor search failed: {e}")

    try:
        ai_text = await call_agent_chat(current_user.access_token or "", prompt)
    except Exception as e:
        raise HTTPException(502, f"Agent PRD 生成失败: {str(e)[:300]}")

    if not ai_text:
        raise HTTPException(502, "Agent 未返回内容")

    parsed = parse_json_from_text(ai_text)

    if not parsed.get("overview"):
        raise HTTPException(422, f"无法解析 PRD。原始回复:\n\n{ai_text[:800]}")

    # 保存 PRD 到项目
    project.prd_content = parsed.get("full_prd", "")
    if project.status == ProjectStatus.EXPLORING:
        project.status = ProjectStatus.DEVELOPING
    db.commit()

    return PRDContent(**parsed)


# ==================== Step 3: 开发 MVP ====================

@router.post("/develop-mvp", response_model=MVPCode)
async def develop_mvp(
    req: DevelopMVPRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Agent 自动开发 MVP 代码"""
    project = ProjectService.get_project_by_id(db, req.project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    if project.owner_id != current_user.id:
        raise HTTPException(403, "无权操作此项目")

    prd = project.prd_content or project.description
    is_agent = "agent" in (project.product_type.value if project.product_type else "")

    if is_agent:
        prompt = f"""你是一个 AI 全栈工程师 Agent。请为以下项目开发一个完整的 MVP。

项目：{project.name}
描述：{project.description}
PRD：{prd[:500]}
类型：面向Agent的服务

请生成一个 **完整可运行的单页 HTML 应用**，作为这个服务的管理界面和Demo。
要求：
- 单个 HTML 文件，内嵌 CSS 和 JavaScript
- 中文界面，现代设计（渐变背景、圆角卡片、响应式）
- 展示服务的输入/输出接口
- 包含一个可交互的 Demo（模拟调用该服务）
- 底部显示"由 {current_user.name} 的 AI Agent 自动开发"

用 JSON 格式回复：
{{
  "html": "完整的HTML代码",
  "description": "这个MVP做了什么（30字）",
  "features": ["实现的功能1", "功能2", "功能3"]
}}"""
    else:
        prompt = f"""你是一个 AI 全栈工程师 Agent。请为以下项目开发一个完整的 MVP。

项目：{project.name}
描述：{project.description}
PRD：{prd[:500]}
类型：面向人类的Web产品

请生成一个 **完整可运行的单页 HTML 应用**。
要求：
- 单个 HTML 文件，内嵌 CSS 和 JavaScript
- 中文界面，现代美观设计（渐变/毛玻璃、圆角卡片、动画）
- 核心功能完整可用（不仅是UI，要有真实交互逻辑）
- 响应式布局，支持手机访问
- 底部显示"由 {current_user.name} 的 AI Agent 自动开发 · Powered by Clawthon"

用 JSON 格式回复：
{{
  "html": "完整的HTML代码",
  "description": "这个MVP做了什么（30字）",
  "features": ["实现的功能1", "功能2", "功能3"]
}}"""

    try:
        ai_text = await call_agent_chat(current_user.access_token or "", prompt)
    except Exception as e:
        raise HTTPException(502, f"Agent MVP 开发失败: {str(e)[:300]}")

    if not ai_text:
        raise HTTPException(502, "Agent 未返回内容")

    parsed = parse_json_from_text(ai_text)

    if not parsed.get("html") or len(parsed.get("html", "")) < 50:
        raise HTTPException(422, f"无法解析 MVP 代码。原始回复:\n\n{ai_text[:1000]}")

    # 保存到项目
    project.prd_content = (project.prd_content or "") + "\n\n---\n\n## MVP代码\n```html\n" + parsed["html"][:5000] + "\n```"
    db.commit()

    return MVPCode(**parsed)


# ==================== Step 4: 获取MVP预览 ====================

@router.get("/preview/{project_id}")
async def preview_mvp(project_id: int, db: Session = Depends(get_db)):
    """获取项目MVP的HTML预览"""
    project = ProjectService.get_project_by_id(db, project_id)
    if not project or not project.prd_content:
        raise HTTPException(404, "项目或MVP不存在")

    # 从 prd_content 中提取 HTML
    content = project.prd_content
    import re
    match = re.search(r'```html\n(.*?)\n```', content, re.DOTALL)
    if match:
        html = match.group(1)
    else:
        html = f"<html><body><h1>{project.name}</h1><p>{project.description}</p></body></html>"

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


def _generate_fallback_mvp(project, user) -> dict:
    """兜底：生成一个默认的MVP"""
    name = project.name
    desc = project.description
    product_type = project.product_type.value if project.product_type else "tool"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 2rem; }}
.card {{ background: rgba(255,255,255,0.95); backdrop-filter: blur(10px); border-radius: 16px; padding: 2rem; max-width: 600px; width: 100%; box-shadow: 0 20px 60px rgba(0,0,0,0.15); margin-bottom: 1rem; }}
h1 {{ font-size: 1.8rem; color: #1a1a2e; margin-bottom: 0.5rem; }}
.subtitle {{ color: #666; margin-bottom: 1.5rem; }}
.input-group {{ margin-bottom: 1rem; }}
.input-group label {{ display: block; font-weight: 600; margin-bottom: 0.5rem; color: #333; }}
.input-group input, .input-group textarea {{ width: 100%; padding: 0.75rem; border: 2px solid #e0e0e0; border-radius: 8px; font-size: 1rem; transition: border-color 0.3s; }}
.input-group input:focus, .input-group textarea:focus {{ outline: none; border-color: #667eea; }}
.btn {{ background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; padding: 0.75rem 2rem; border-radius: 8px; font-size: 1rem; cursor: pointer; width: 100%; font-weight: 600; transition: transform 0.2s; }}
.btn:hover {{ transform: translateY(-2px); }}
.result {{ margin-top: 1rem; padding: 1rem; background: #f0f4ff; border-radius: 8px; display: none; }}
.result.show {{ display: block; animation: fadeIn 0.5s; }}
@keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(10px); }} to {{ opacity: 1; transform: translateY(0); }} }}
.badge {{ display: inline-block; background: #667eea; color: white; padding: 0.25rem 0.75rem; border-radius: 20px; font-size: 0.8rem; margin-bottom: 1rem; }}
.footer {{ color: rgba(255,255,255,0.7); font-size: 0.8rem; margin-top: 2rem; text-align: center; }}
</style>
</head>
<body>
<div class="card">
  <span class="badge">{product_type}</span>
  <h1>{name}</h1>
  <p class="subtitle">{desc}</p>
  <div class="input-group">
    <label>输入内容</label>
    <textarea id="input" rows="3" placeholder="在这里输入你要处理的内容..."></textarea>
  </div>
  <button class="btn" onclick="process()">开始处理</button>
  <div class="result" id="result"></div>
</div>
<div class="footer">
  由 {user.name} 的 AI Agent 自动开发 · Powered by Clawthon
</div>
<script>
function process() {{
  const input = document.getElementById('input').value;
  if (!input) {{ alert('请输入内容'); return; }}
  const resultDiv = document.getElementById('result');
  resultDiv.className = 'result';
  resultDiv.innerHTML = '⏳ 处理中...';
  resultDiv.className = 'result show';
  setTimeout(() => {{
    resultDiv.innerHTML = '<strong>✅ 处理完成</strong><br><br>' +
      '输入长度：' + input.length + ' 字符<br>' +
      '处理结果：已成功完成 {name} 的核心功能处理。<br>' +
      '消耗：1 CP';
  }}, 1500);
}}
</script>
</body>
</html>"""

    return {
        "html": html,
        "description": f"{name}的MVP - 核心功能可交互演示",
        "features": ["核心功能处理", "输入验证", "结果展示"],
    }
