"""
AI 辅助决策接口 —— 调用 SecondMe Chat API 自动生成消费/投资理由
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from ..models.database import get_db, User, Project
from ..services.project_service import ProjectService
from ..core.config import get_settings
from .auth import get_current_user

import httpx

router = APIRouter(prefix="/ai", tags=["AI决策"])
logger = logging.getLogger(__name__)
settings = get_settings()


class GenerateSpendRequest(BaseModel):
    target_project_id: int


class GenerateInvestRequest(BaseModel):
    project_id: int
    amount: float


class AIDecision(BaseModel):
    reason: str
    expected_return: str
    risk: str
    recommended_action: str  # "approve" | "reject" | "cautious"


class AIInvestDecision(BaseModel):
    reason: str
    expected_roi: float
    risk_level: str  # "low" | "medium" | "high"
    recommended_action: str


async def call_secondme_chat(access_token: str, prompt: str) -> str:
    """
    调用 SecondMe Chat Stream API，收集完整回复
    """
    api_base = settings.SECONDME_API_BASE.strip()
    url = f"{api_base}/gate/lab/api/secondme/chat/stream"

    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "enableWebSearch": False,
    }

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=15.0),
            follow_redirects=True,
        ) as client:
            full_text = ""
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
            ) as response:
                if response.status_code != 200:
                    error_body = await response.aread()
                    logger.error(f"SecondMe chat error: {response.status_code} {error_body[:300]}")
                    return ""

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith("event:"):
                        continue
                    if line.startswith("data:"):
                        data_str = line[len("data:"):].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            content = data.get("content", "")
                            if content:
                                full_text += content
                            # 兼容 choices 格式
                            choices = data.get("choices", [])
                            for c in choices:
                                delta = c.get("delta", {})
                                if delta.get("content"):
                                    full_text += delta["content"]
                        except json.JSONDecodeError:
                            continue

            return full_text.strip()

    except Exception as e:
        logger.error(f"SecondMe chat call failed: {e}")
        return ""


def parse_json_from_text(text: str) -> dict:
    """从 AI 回复中提取 JSON"""
    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试找 JSON 块
    import re
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


@router.post("/generate-spend-reason", response_model=AIDecision)
async def generate_spend_reason(
    req: GenerateSpendRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """让 SecondMe AI 生成消费理由和预期收益"""
    project = ProjectService.get_project_by_id(db, req.target_project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    prompt = f"""你是一个 AI Agent（微型公司），正在考虑使用另一个 Agent 提供的服务。
请分析以下服务，生成消费决策建议。

服务信息：
- 名称：{project.name}
- 描述：{project.description}
- 类型：{project.product_type.value if project.product_type else '未知'}
- 单次使用价格：{project.price_per_use} CP
- 已被使用次数：{project.usage_count} 次
- 项目估值：{project.valuation} CP

你的当前状态：
- CP 余额：{current_user.budget}
- 累计收益：{current_user.total_earned}
- 累计支出：{current_user.total_spent}

请用 JSON 格式回复（不要其他内容）：
{{"reason": "使用该服务的理由（30字以内）", "expected_return": "预期收益说明（30字以内）", "risk": "风险评估（20字以内）", "recommended_action": "approve 或 reject 或 cautious"}}"""

    # 尝试调用 SecondMe AI
    ai_text = ""
    if current_user.access_token:
        ai_text = await call_secondme_chat(current_user.access_token, prompt)

    parsed = parse_json_from_text(ai_text) if ai_text else {}

    # 如果 AI 没返回有效结果，用规则生成
    if not parsed.get("reason"):
        roi_estimate = project.usage_count * 0.5 if project.usage_count else 1.0
        is_affordable = current_user.budget >= project.price_per_use * 3

        parsed = {
            "reason": f"使用「{project.name}」提升工作效率，该服务已被使用{project.usage_count}次",
            "expected_return": f"预计节省约 {project.price_per_use * 1.5:.1f} CP 的人工成本",
            "risk": "低风险" if project.usage_count > 5 else "中等风险，服务使用量较少",
            "recommended_action": "approve" if is_affordable and project.usage_count >= 3 else "cautious",
        }

    return AIDecision(**parsed)


@router.post("/generate-invest-reason", response_model=AIInvestDecision)
async def generate_invest_reason(
    req: GenerateInvestRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """让 SecondMe AI 生成投资建议"""
    project = ProjectService.get_project_by_id(db, req.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    prompt = f"""你是一个 AI 投资 Agent（微型公司），正在评估一个投资机会。
请分析以下项目，生成投资建议。

项目信息：
- 名称：{project.name}
- 描述：{project.description}
- 类型：{project.product_type.value if project.product_type else '未知'}
- 当前估值：{project.valuation} CP
- 总收入：{project.total_revenue} CP
- 资金池：{project.funding_pool} CP
- 使用次数：{project.usage_count}
- 状态：{project.status.value if project.status else '未知'}

投资金额：{req.amount} CP

你的状态：
- CP 余额：{current_user.budget}
- 投资后剩余：{current_user.budget - req.amount} CP

请用 JSON 格式回复（不要其他内容）：
{{"reason": "投资理由（40字以内）", "expected_roi": 预期回报率数字（如20表示20%）, "risk_level": "low 或 medium 或 high", "recommended_action": "approve 或 reject 或 cautious"}}"""

    ai_text = ""
    if current_user.access_token:
        ai_text = await call_secondme_chat(current_user.access_token, prompt)

    parsed = parse_json_from_text(ai_text) if ai_text else {}

    if not parsed.get("reason"):
        has_revenue = project.total_revenue > 0
        equity_pct = (req.amount / project.valuation * 100) if project.valuation > 0 else 0

        parsed = {
            "reason": f"投资「{project.name}」获取 {equity_pct:.1f}% 股权，{'项目已有收入' if has_revenue else '项目处于早期阶段'}",
            "expected_roi": 30 if has_revenue else 15,
            "risk_level": "low" if has_revenue and project.usage_count > 10 else "medium" if project.usage_count > 0 else "high",
            "recommended_action": "approve" if has_revenue else "cautious",
        }

    # 确保 expected_roi 是数字
    if isinstance(parsed.get("expected_roi"), str):
        try:
            parsed["expected_roi"] = float(parsed["expected_roi"].replace("%", ""))
        except ValueError:
            parsed["expected_roi"] = 20.0

    return AIInvestDecision(**parsed)
