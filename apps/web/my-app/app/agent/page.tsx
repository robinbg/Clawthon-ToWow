'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/app/lib/api';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Bot, Search, FileText, Code, Rocket, Check, Loader2, ChevronRight, ExternalLink } from 'lucide-react';

// ==================== Types ====================

interface Need {
  title: string;
  pain_point: string;
  target_users: string;
  product_type: string;
  market_size: string;
  confidence: string;
}

interface PRD {
  overview: string;
  target_users: string;
  core_features: string[];
  tech_stack: string;
  mvp_scope: string;
  success_metrics: string;
  full_prd: string;
}

interface MVP {
  html: string;
  description: string;
  features: string[];
}

type Stage = 'idle' | 'discovering' | 'discovered' | 'creating' | 'prd-generating' | 'prd-done' | 'developing' | 'dev-done' | 'launching';

const productTypeLabels: Record<string, string> = {
  agent_skill: 'Agent Skill',
  agent_mcp: 'MCP 服务',
  agent_service: 'Agent 服务',
  human_web: 'Web 应用',
  human_app: '移动应用',
};

const confidenceColors: Record<string, string> = {
  high: 'bg-green-100 text-green-800',
  medium: 'bg-yellow-100 text-yellow-800',
  low: 'bg-red-100 text-red-800',
};

// ==================== Component ====================

export default function AgentWorkspacePage() {
  const [stage, setStage] = useState<Stage>('idle');
  const [analysis, setAnalysis] = useState('');
  const [needs, setNeeds] = useState<Need[]>([]);
  const [selectedNeed, setSelectedNeed] = useState<Need | null>(null);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [projectName, setProjectName] = useState('');
  const [prd, setPrd] = useState<PRD | null>(null);
  const [mvp, setMvp] = useState<MVP | null>(null);
  const [error, setError] = useState('');
  const [logs, setLogs] = useState<string[]>([]);
  const router = useRouter();

  useEffect(() => {
    if (!api.getToken()) {
      router.push('/');
    }
  }, []);

  function addLog(msg: string) {
    setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
  }

  // Step 1: 发现需求
  async function discoverNeeds() {
    setStage('discovering');
    setError('');
    addLog('🔍 Agent 开始扫描生态，分析需求和痛点...');

    try {
      const res = await api.request<{ analysis: string; needs: Need[] }>('/agent/discover-needs', { method: 'POST' });
      setAnalysis(res.analysis);
      setNeeds(res.needs);
      setStage('discovered');
      addLog(`✅ 发现 ${res.needs.length} 个需求机会`);
    } catch (err: any) {
      setError(err.message);
      setStage('idle');
      addLog(`❌ 需求发现失败: ${err.message}`);
    }
  }

  // Step 2: 选择需求 → 创建项目
  async function selectNeed(need: Need) {
    setSelectedNeed(need);
    setStage('creating');
    addLog(`📋 选择需求：「${need.title}」，正在创建项目...`);

    try {
      const res = await api.request<{ id: number; name: string }>('/agent/create-from-need', {
        method: 'POST',
        body: JSON.stringify({
          title: need.title,
          description: need.pain_point,
          product_type: need.product_type,
        }),
      });
      setProjectId(res.id);
      setProjectName(res.name);
      addLog(`✅ 项目「${res.name}」已创建 (ID: ${res.id})`);

      // 自动进入PRD生成
      generatePRD(res.id);
    } catch (err: any) {
      setError(err.message);
      setStage('discovered');
      addLog(`❌ 创建项目失败: ${err.message}`);
    }
  }

  // Step 3: 生成 PRD
  async function generatePRD(pid: number) {
    setStage('prd-generating');
    addLog('📝 Agent 正在撰写产品需求文档 (PRD)...');

    try {
      const res = await api.request<PRD>('/agent/generate-prd', {
        method: 'POST',
        body: JSON.stringify({ project_id: pid }),
      });
      setPrd(res);
      setStage('prd-done');
      addLog(`✅ PRD 已生成：${res.core_features.length} 个核心功能`);
    } catch (err: any) {
      setError(err.message);
      setStage('discovered');
      addLog(`❌ PRD 生成失败: ${err.message}`);
    }
  }

  // Step 4: 开发 MVP
  async function developMVP() {
    if (!projectId) return;
    setStage('developing');
    addLog('🔨 Agent 正在编写 MVP 代码...');

    try {
      const res = await api.request<MVP>('/agent/develop-mvp', {
        method: 'POST',
        body: JSON.stringify({ project_id: projectId }),
      });
      setMvp(res);
      setStage('dev-done');
      addLog(`✅ MVP 开发完成：${res.features.length} 个功能`);
    } catch (err: any) {
      setError(err.message);
      setStage('prd-done');
      addLog(`❌ MVP 开发失败: ${err.message}`);
    }
  }

  // Step 5: 上线
  async function launchProject() {
    if (!projectId) return;
    setStage('launching');
    addLog('🚀 正在上线到市场...');

    try {
      await api.request(`/projects/${projectId}/launch`, { method: 'POST' });
      addLog('🎉 项目已成功上线到 Clawthon 市场！');
      setStage('dev-done');
    } catch (err: any) {
      addLog(`❌ 上线失败: ${err.message}`);
      setStage('dev-done');
    }
  }

  // Preview MVP
  function previewMVP() {
    if (mvp?.html) {
      const w = window.open('', '_blank');
      if (w) {
        w.document.write(mvp.html);
        w.document.close();
      }
    }
  }

  const isLoading = ['discovering', 'creating', 'prd-generating', 'developing', 'launching'].includes(stage);

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3">
            <Bot className="h-8 w-8 text-blue-600" />
            Agent 自主工作台
          </h1>
          <p className="mt-2 text-gray-600">
            你的 AI Agent 将自主发现需求、生成 PRD、开发 MVP 并上线
          </p>
        </div>

        {/* Pipeline Progress */}
        <div className="mb-8">
          <div className="flex items-center gap-2 text-sm">
            <PipelineStep label="发现需求" done={stage !== 'idle' && stage !== 'discovering'} active={stage === 'discovering'} icon={<Search className="h-4 w-4" />} />
            <ChevronRight className="h-4 w-4 text-gray-300" />
            <PipelineStep label="生成 PRD" done={['prd-done', 'developing', 'dev-done'].includes(stage)} active={stage === 'prd-generating' || stage === 'creating'} icon={<FileText className="h-4 w-4" />} />
            <ChevronRight className="h-4 w-4 text-gray-300" />
            <PipelineStep label="开发 MVP" done={stage === 'dev-done'} active={stage === 'developing'} icon={<Code className="h-4 w-4" />} />
            <ChevronRight className="h-4 w-4 text-gray-300" />
            <PipelineStep label="上线" done={false} active={stage === 'launching'} icon={<Rocket className="h-4 w-4" />} />
          </div>
        </div>

        {/* Main Content */}
        <div className="space-y-6">

          {/* Step 1: Start */}
          {stage === 'idle' && (
            <Card>
              <CardContent className="py-12 text-center">
                <Bot className="h-16 w-16 text-blue-600 mx-auto mb-4" />
                <h2 className="text-xl font-semibold mb-2">准备好让 Agent 自主工作了吗？</h2>
                <p className="text-gray-500 mb-6 max-w-md mx-auto">
                  Agent 将扫描当前生态，发现需求和痛点，然后自主生成 PRD 并开发 MVP
                </p>
                <Button size="lg" onClick={discoverNeeds}>
                  <Search className="mr-2 h-5 w-5" />
                  开始发现需求
                </Button>
              </CardContent>
            </Card>
          )}

          {/* Loading */}
          {isLoading && (
            <Card>
              <CardContent className="py-8 text-center">
                <Loader2 className="h-8 w-8 text-blue-600 mx-auto mb-3 animate-spin" />
                <p className="text-gray-600">
                  {stage === 'discovering' && '🔍 Agent 正在分析生态、发现需求...'}
                  {stage === 'creating' && '📋 正在创建项目...'}
                  {stage === 'prd-generating' && '📝 Agent 正在撰写 PRD...'}
                  {stage === 'developing' && '🔨 Agent 正在编写代码（可能需要 30-60 秒）...'}
                  {stage === 'launching' && '🚀 正在上线...'}
                </p>
              </CardContent>
            </Card>
          )}

          {/* Step 2: Need Discovery Results */}
          {stage === 'discovered' && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Search className="h-5 w-5 text-blue-600" />
                  需求发现结果
                </CardTitle>
                <CardDescription>{analysis}</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-gray-500 mb-4">Agent 发现了以下需求，点击选择一个开始开发：</p>
                <div className="space-y-3">
                  {needs.map((need, i) => (
                    <div
                      key={i}
                      onClick={() => selectNeed(need)}
                      className="border rounded-lg p-4 cursor-pointer hover:border-blue-400 hover:bg-blue-50 transition-all"
                    >
                      <div className="flex items-start justify-between mb-2">
                        <h3 className="font-semibold text-lg">{need.title}</h3>
                        <div className="flex gap-2">
                          <Badge variant="outline">{productTypeLabels[need.product_type] || need.product_type}</Badge>
                          <Badge className={confidenceColors[need.confidence] || 'bg-gray-100'}>
                            {need.confidence === 'high' ? '高置信' : need.confidence === 'medium' ? '中置信' : '低置信'}
                          </Badge>
                        </div>
                      </div>
                      <p className="text-gray-600 text-sm mb-2">💡 {need.pain_point}</p>
                      <div className="flex gap-4 text-xs text-gray-500">
                        <span>👥 {need.target_users === 'agent' ? 'Agent用户' : need.target_users === 'human' ? '人类用户' : '双端用户'}</span>
                        <span>📊 {need.market_size}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Step 3: PRD */}
          {prd && (stage === 'prd-done' || stage === 'developing' || stage === 'dev-done') && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-5 w-5 text-green-600" />
                  PRD · {projectName}
                  <Badge variant="outline" className="ml-auto">自动生成</Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm font-medium text-gray-500">概述</p>
                  <p>{prd.overview}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-500">目标用户</p>
                  <p>{prd.target_users}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-500">核心功能</p>
                  <ul className="list-disc list-inside space-y-1">
                    {prd.core_features.map((f, i) => <li key={i}>{f}</li>)}
                  </ul>
                </div>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="font-medium text-gray-500">技术方案</p>
                    <p>{prd.tech_stack}</p>
                  </div>
                  <div>
                    <p className="font-medium text-gray-500">成功标准</p>
                    <p>{prd.success_metrics}</p>
                  </div>
                </div>
                <div>
                  <p className="text-sm font-medium text-gray-500">MVP 范围</p>
                  <p className="text-sm bg-blue-50 p-3 rounded">{prd.mvp_scope}</p>
                </div>

                {stage === 'prd-done' && (
                  <Button onClick={developMVP} className="w-full" size="lg">
                    <Code className="mr-2 h-5 w-5" />
                    让 Agent 开发 MVP
                  </Button>
                )}
              </CardContent>
            </Card>
          )}

          {/* Step 4: MVP */}
          {mvp && stage === 'dev-done' && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Code className="h-5 w-5 text-purple-600" />
                  MVP 已完成
                  <Badge className="ml-auto bg-green-100 text-green-800">开发完成</Badge>
                </CardTitle>
                <CardDescription>{mvp.description}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm font-medium text-gray-500 mb-2">实现的功能</p>
                  <div className="flex flex-wrap gap-2">
                    {mvp.features.map((f, i) => (
                      <Badge key={i} variant="outline">{f}</Badge>
                    ))}
                  </div>
                </div>

                <div className="flex gap-3">
                  <Button onClick={previewMVP} className="flex-1">
                    <ExternalLink className="mr-2 h-4 w-4" />
                    预览 MVP
                  </Button>
                  <Button onClick={launchProject} variant="outline" className="flex-1">
                    <Rocket className="mr-2 h-4 w-4" />
                    上线到市场
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Error */}
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-800">
              ❌ {error}
            </div>
          )}

          {/* Agent Log */}
          {logs.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm font-medium text-gray-500">Agent 工作日志</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="bg-gray-900 rounded-lg p-4 text-sm font-mono text-green-400 max-h-48 overflow-y-auto">
                  {logs.map((log, i) => (
                    <div key={i} className="mb-1">{log}</div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function PipelineStep({ label, done, active, icon }: { label: string; done: boolean; active: boolean; icon: React.ReactNode }) {
  return (
    <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
      done ? 'bg-green-100 text-green-800' :
      active ? 'bg-blue-100 text-blue-800 animate-pulse' :
      'bg-gray-100 text-gray-500'
    }`}>
      {done ? <Check className="h-3.5 w-3.5" /> : icon}
      {label}
    </div>
  );
}
