#!/usr/bin/env python3
"""发现市场需求和创业机会"""
import sys
import json

def main():
    keyword = sys.argv[1] if len(sys.argv) > 1 else ""
    
    result = {
        "action": "discover_needs",
        "keyword": keyword,
        "api_endpoint": "POST /agent/discover-needs",
        "description": "Agent 自主分析互联网趋势，发现可行的产品需求",
        "output_format": {
            "analysis": "调研分析",
            "needs": [
                {
                    "title": "需求名称",
                    "pain_point": "痛点描述",
                    "target_users": "human|agent|both",
                    "product_type": "agent_skill|agent_mcp|human_web",
                    "market_size": "规模评估",
                    "confidence": "high|medium|low"
                }
            ]
        }
    }
    
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
