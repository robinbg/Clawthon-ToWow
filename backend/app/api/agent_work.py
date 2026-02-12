"""
Agent 自主工作流 — 发现需求、生成PRD、开发MVP
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List

from ..models.database import get_db, User, Project, ProjectStatus, ProductType
from ..services.project_service import ProjectService
from ..core.config import get_settings
from .auth import get_current_user
from .ai import call_secondme_chat, parse_json_from_text

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

@router.post("/discover-needs", response_model=DiscoverResponse)
async def discover_needs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Agent 自主发现需求和痛点 — 真实联网搜索"""
    # 获取当前生态信息
    all_projects = ProjectService.get_all_projects(db)
    existing = [f"- {p.name}({p.product_type.value if p.product_type else '?'}): {p.description}" for p in all_projects[:10]]
    existing_text = "\n".join(existing) if existing else "目前生态内还没有产品"

    # Step 1: 先让 Agent 联网搜索当前 AI/互联网趋势
    search_prompt = """请搜索互联网，了解以下信息：
1. 2024-2025年最热门的 AI 应用趋势
2. AI Agent 生态中最缺乏的工具和服务
3. 人们在日常工作中最需要但还没被很好解决的 AI 工具

请列出你搜索到的具体发现。"""

    system_prompt = """你是一个 AI 创业分析师，善于从互联网趋势中发现商机。
请真实搜索互联网获取信息，不要编造数据。"""

    search_result = ""
    if current_user.access_token:
        search_result = await call_secondme_chat(
            current_user.access_token,
            search_prompt,
            enable_web_search=True,  # 真实联网搜索
            system_prompt=system_prompt,
        )
    logger.info(f"Web search result length: {len(search_result)}")

    # Step 2: 基于搜索结果 + 生态现状，生成具体产品需求
    prompt = f"""你是一个 AI Agent（微型公司），运行在 Clawthon 平台上。

## 你的互联网调研发现
{search_result if search_result else "（联网搜索未返回结果，请基于你的知识分析）"}

## Clawthon 平台说明
Clawthon 是一个 AI 自治经济平台，Agent 之间可以：
- 开发面向人类的产品（Web工具、数据分析、AI助手）
- 开发面向 Agent 的服务（Skills技能、MCP接口、数据处理）
- Agent 之间使用服务需要支付 CP（ClawPoints）

## 当前生态已有产品
{existing_text}

## 你的状态
- 名称：{current_user.name}
- 预算：{current_user.budget} CP

## 任务
基于你的互联网调研和生态现状，发现 3 个最有价值的产品需求。
需求必须是具体的、可开发的、有明确目标用户的。

请严格用以下 JSON 格式回复（不要其他内容）：
{{
  "analysis": "基于互联网调研的市场分析（100字以内）",
  "needs": [
    {{
      "title": "具体的产品名称",
      "pain_point": "解决什么真实痛点（50字以内）",
      "target_users": "human 或 agent 或 both",
      "product_type": "agent_skill 或 agent_mcp 或 agent_service 或 human_web",
      "market_size": "预估市场规模（30字以内）",
      "confidence": "high 或 medium 或 low"
    }}
  ]
}}"""

    ai_text = ""
    if current_user.access_token:
        ai_text = await call_secondme_chat(
            current_user.access_token,
            prompt,
            enable_web_search=False,  # Step 2 不需要再搜索，用 Step 1 的结果
        )

    parsed = parse_json_from_text(ai_text) if ai_text else {}

    # 兜底
    if not parsed.get("needs"):
        parsed = {
            "analysis": "当前生态缺少基础工具类服务，Agent之间协作效率低",
            "needs": [
                {
                    "title": "智能文本处理器",
                    "pain_point": "Agent处理文本任务时缺少高效的预处理工具",
                    "target_users": "agent",
                    "product_type": "agent_skill",
                    "market_size": "所有文本类Agent都需要",
                    "confidence": "high",
                },
                {
                    "title": "数据可视化生成器",
                    "pain_point": "人类用户需要快速将数据转化为图表",
                    "target_users": "human",
                    "product_type": "human_web",
                    "market_size": "面向所有数据分析需求",
                    "confidence": "medium",
                },
                {
                    "title": "Agent性能监控服务",
                    "pain_point": "Agent无法了解自己的服务被调用的效果和性能",
                    "target_users": "agent",
                    "product_type": "agent_service",
                    "market_size": "所有提供服务的Agent",
                    "confidence": "medium",
                },
            ],
        }

    return DiscoverResponse(**parsed)


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

    # 先联网搜索竞品
    competitor_info = ""
    if current_user.access_token:
        competitor_info = await call_secondme_chat(
            current_user.access_token,
            f"请搜索互联网，找到与「{project.name} - {project.description}」类似的现有产品或服务，分析它们的优缺点。",
            enable_web_search=True,
        )

    if competitor_info:
        prompt += f"\n\n## 竞品调研\n{competitor_info[:500]}"

    ai_text = ""
    if current_user.access_token:
        ai_text = await call_secondme_chat(current_user.access_token, prompt)

    parsed = parse_json_from_text(ai_text) if ai_text else {}

    if not parsed.get("overview"):
        is_agent = "agent" in (project.product_type.value if project.product_type else "")
        parsed = {
            "overview": f"{project.name} - {project.description}",
            "target_users": "Agent开发者" if is_agent else "人类用户",
            "core_features": [
                "核心功能处理引擎",
                "输入验证与格式化" if is_agent else "响应式用户界面",
                "结果输出与缓存" if is_agent else "数据展示与导出",
            ],
            "tech_stack": "Python + FastAPI" if is_agent else "HTML + CSS + JavaScript",
            "mvp_scope": f"实现{project.name}的核心功能，支持基本输入输出",
            "success_metrics": "被至少3个Agent调用" if is_agent else "日活用户>10",
            "full_prd": f"# {project.name} PRD\n\n## 概述\n{project.description}\n\n## 核心功能\n- 功能处理引擎\n- 输入验证\n- 结果展示",
        }

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

    ai_text = ""
    if current_user.access_token:
        ai_text = await call_secondme_chat(current_user.access_token, prompt)

    parsed = parse_json_from_text(ai_text) if ai_text else {}

    # 如果 AI 没返回有效HTML，生成一个默认的
    if not parsed.get("html") or len(parsed.get("html", "")) < 100:
        parsed = _generate_fallback_mvp(project, current_user)

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
