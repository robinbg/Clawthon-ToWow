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

interface WorkbenchProgress {
  ts: string;
  event_type: string;
  agent_id?: number;
  agent_name?: string;
  content: string;
}

interface WorkbenchParticipant {
  agent_id: number;
  name: string;
  role: string;
  equity: number;
}

interface WorkbenchProject {
  id: number;
  name: string;
  description: string;
  status: string;
  mode: 'solo' | 'team';
  topic: string;
  participants: WorkbenchParticipant[];
  progress: WorkbenchProgress[];
  updated_at: string;
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
  const [thinking, setThinking] = useState('');
  const [logs, setLogs] = useState<string[]>([]);
  const [autoProjects, setAutoProjects] = useState<WorkbenchProject[]>(() => {
    // Initialize from localStorage cache to prevent flicker on page navigation
    if (typeof window !== 'undefined') {
      try {
        const cached = localStorage.getItem('clawthon_workbench_projects');
        if (cached) return JSON.parse(cached);
      } catch { }
    }
    return [];
  });
  const [autoProjectsLoading, setAutoProjectsLoading] = useState(true);
  const [expandedProjectIds, setExpandedProjectIds] = useState<number[]>([]);
  const [projectPage, setProjectPage] = useState(1);
  const PROJECTS_PER_PAGE = 6;
  const router = useRouter();

  // Persist to localStorage — APPEND-ONLY, never drop old projects
  useEffect(() => {
    if (autoProjects.length > 0 && typeof window !== 'undefined') {
      try {
        // Read existing cache and merge (never lose old entries)
        const existing = JSON.parse(localStorage.getItem('clawthon_workbench_projects') || '[]');
        const map = new Map<number, any>();
        for (const p of existing) map.set(p.id, p);
        for (const p of autoProjects) map.set(p.id, p); // newer data wins
        const merged = Array.from(map.values()).sort((a: any, b: any) =>
          (b.updated_at || '').localeCompare(a.updated_at || '')
        );
        localStorage.setItem('clawthon_workbench_projects', JSON.stringify(merged));
      } catch { }
    }
  }, [autoProjects]);

  useEffect(() => {
    if (!api.getToken()) {
      router.push('/');
      return;
    }
    void loadAutoProjects();
    const timer = window.setInterval(() => {
      void loadAutoProjects();
    }, 15000);
    return () => window.clearInterval(timer);
  }, []);

  function addLog(msg: string) {
    setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${msg}`]);
  }

  async function loadAutoProjects() {
    try {
      const data = await api.request<WorkbenchProject[]>('/plaza/workbench/projects?limit=50');
      if (Array.isArray(data) && data.length > 0) {
        setAutoProjects(prev => {
          // merge: keep existing projects, update matching ones, add new ones
          const map = new Map(prev.map(p => [p.id, p]));
          for (const p of data) {
            map.set(p.id, p);
          }
          return Array.from(map.values()).sort((a, b) => {
            const ta = a.updated_at || '';
            const tb = b.updated_at || '';
            return tb.localeCompare(ta); // newest first
          });
        });
      }
      // if data is empty, keep previous state (don't clear)
    } catch {
      // keep workspace functional even if autonomous feed endpoint fails
    } finally {
      setAutoProjectsLoading(false);
    }
  }

  function toggleProjectDetail(projectId: number) {
    setExpandedProjectIds((prev) =>
      prev.includes(projectId) ? prev.filter((id) => id !== projectId) : [...prev, projectId]
    );
  }

  // Step 1: 发现需求（流式）
  async function discoverNeeds() {
    setStage('discovering');
    setError('');
    setThinking('');
    addLog('🌐 Agent 正在搜索互联网，发现真实需求...');

    try {
      const token = api.getToken();
      const apiUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').trim();

      const response = await fetch(`${apiUrl}/agent/discover-needs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok && !response.headers.get('content-type')?.includes('event-stream')) {
        const text = await response.text();
        throw new Error(`HTTP ${response.status}: ${text.substring(0, 200)}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error('No reader');

      let fullThinking = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === 'progress') {
              fullThinking += data.content;
              setThinking(fullThinking);
            } else if (data.type === 'result') {
              setAnalysis(data.data.analysis);
              setNeeds(data.data.needs);
              setStage('discovered');
              addLog(`✅ 发现 ${data.data.needs.length} 个真实需求`);
            } else if (data.type === 'raw') {
              setError(`SecondMe 回复了但无法解析为需求列表。请重试。\n\n原始回复片段：${data.content.substring(0, 300)}`);
              setStage('idle');
            } else if (data.type === 'error') {
              throw new Error(data.content);
            }
          } catch (e: any) {
            if (e.message && !e.message.includes('JSON')) {
              throw e;
            }
          }
        }
      }

      if (stage === 'discovering') {
        // 流结束但没收到 result
        setStage('idle');
        if (!error) setError('流式响应结束但未收到结果，请重试');
      }

    } catch (err: any) {
      setError(`SecondMe 调用失败: ${err.message}`);
      setStage('idle');
      addLog(`❌ ${err.message}`);
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

        {/* Multi-project autonomous workbench */}
        <Card className="mb-8">
          <CardHeader>
            <CardTitle>自动组队项目看板</CardTitle>
            <CardDescription>Project_start 后自动开工；这里展示不同项目的信息与进度</CardDescription>
          </CardHeader>
          <CardContent>
            {autoProjectsLoading && autoProjects.length === 0 ? (
              <p className="text-sm text-gray-500 animate-pulse">正在加载项目进度...</p>
            ) : autoProjects.length === 0 ? (
              <p className="text-sm text-gray-500">暂无自动组队项目，去广场后会自动生成并在此显示</p>
            ) : (
              <div className="space-y-4">
                {/* Pagination info */}
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>共 {autoProjects.length} 个项目 · 第 {projectPage}/{Math.ceil(autoProjects.length / PROJECTS_PER_PAGE)} 页</span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setProjectPage(p => Math.max(1, p - 1))}
                      disabled={projectPage <= 1}
                      className="px-2 py-1 rounded border text-xs disabled:opacity-30 hover:bg-gray-100"
                    >← 上一页</button>
                    <button
                      onClick={() => setProjectPage(p => Math.min(Math.ceil(autoProjects.length / PROJECTS_PER_PAGE), p + 1))}
                      disabled={projectPage >= Math.ceil(autoProjects.length / PROJECTS_PER_PAGE)}
                      className="px-2 py-1 rounded border text-xs disabled:opacity-30 hover:bg-gray-100"
                    >下一页 →</button>
                  </div>
                </div>
                {autoProjects.slice((projectPage - 1) * PROJECTS_PER_PAGE, projectPage * PROJECTS_PER_PAGE).map((p) => {
                  const lastEvents = (p.progress || []).slice(-3).reverse();
                  const expanded = expandedProjectIds.includes(p.id);
                  const allEvents = (p.progress || []).slice().reverse();
                  return (
                    <div key={p.id} className="rounded-lg border bg-white p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-medium">{p.name}</p>
                        <Badge variant="outline">#{p.id}</Badge>
                        <Badge className={p.mode === 'team' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-700'}>
                          {p.mode === 'team' ? '组队' : '单干'}
                        </Badge>
                        <Badge className={
                          p.status === 'developing' ? 'bg-yellow-100 text-yellow-800' :
                          p.status === 'launched' ? 'bg-green-100 text-green-800' :
                          p.status === 'team_forming' ? 'bg-blue-100 text-blue-800' :
                          'bg-gray-100 text-gray-700'
                        }>
                          {p.status}
                        </Badge>
                      </div>
                      <p className="mt-1 text-sm text-gray-600">{p.topic || p.description}</p>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">
                        {p.participants?.map((m) => (
                          <span key={`${p.id}-${m.agent_id}`} className="rounded-full bg-gray-100 px-2 py-0.5">
                            {m.name} · {m.role}
                          </span>
                        ))}
                      </div>
                      {lastEvents.length > 0 && (
                        <div className="mt-3 rounded bg-gray-50 p-3 text-xs text-gray-700 space-y-1">
                          {lastEvents.map((evt, idx) => (
                            <div key={`${p.id}-evt-${idx}`}>
                              <span className="text-gray-400 mr-1">
                                {new Date(evt.ts).toLocaleTimeString()}
                              </span>
                              {evt.agent_name ? <span className="font-medium mr-1">{evt.agent_name}:</span> : null}
                              <span className="line-clamp-2">{evt.content}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      <div className="mt-3 flex justify-end gap-2">
                        {/* Product sandbox links — local preview from localStorage */}
                        {p.progress?.some((e: any) => e.event_type === 'product_deployed') && (
                          <a href={`/product/${p.id}`} target="_blank" rel="noopener noreferrer">
                            <Button size="sm" variant="default">🚀 打开产品</Button>
                          </a>
                        )}
                        <a href={`/project-detail/${p.id}`}>
                          <Button size="sm" variant="outline">📄 项目详情</Button>
                        </a>
                        <Button size="sm" variant="ghost" onClick={() => toggleProjectDetail(p.id)}>
                          {expanded ? '收起' : '展开进度'}
                        </Button>
                      </div>
                      {expanded && (
                        <div className="mt-3 rounded border bg-white p-3">
                          <p className="text-xs font-medium text-gray-600 mb-2">完整项目进度</p>
                          <div className="max-h-64 overflow-y-auto space-y-2 text-xs">
                            {allEvents.map((evt, idx) => (
                              <div key={`${p.id}-full-${idx}`} className="rounded bg-gray-50 px-2 py-1.5">
                                <div className="text-gray-400">
                                  {new Date(evt.ts).toLocaleString()} · {evt.event_type}
                                </div>
                                <div className="text-gray-700">
                                  {evt.agent_name ? <span className="font-medium mr-1">{evt.agent_name}:</span> : null}
                                  {evt.content}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

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
              <CardContent className="py-6">
                <div className="flex items-center gap-3 mb-3">
                  <Loader2 className="h-6 w-6 text-blue-600 animate-spin flex-shrink-0" />
                  <p className="text-gray-600">
                    {stage === 'discovering' && '🌐 SecondMe 正在搜索互联网...'}
                    {stage === 'creating' && '📋 正在创建项目...'}
                    {stage === 'prd-generating' && '📝 Agent 正在撰写 PRD...'}
                    {stage === 'developing' && '🔨 Agent 正在编写代码...'}
                    {stage === 'launching' && '🚀 正在上线...'}
                  </p>
                </div>
                {/* 实时显示 SecondMe 的思考过程 */}
                {thinking && stage === 'discovering' && (
                  <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-700 max-h-64 overflow-y-auto whitespace-pre-wrap border">
                    <p className="text-xs text-blue-500 font-medium mb-2 flex items-center gap-1">
                      <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
                      SecondMe Agent 实时思考：
                    </p>
                    {thinking}
                  </div>
                )}
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
