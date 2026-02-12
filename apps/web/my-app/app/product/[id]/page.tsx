'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';

export default function ProductPreviewPage() {
  const params = useParams();
  const id = params.id as string;
  const [code, setCode] = useState<string | null>(null);
  const [productType, setProductType] = useState<string>('');
  const [productName, setProductName] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [callInput, setCallInput] = useState('{"input": "hello"}');
  const [callResult, setCallResult] = useState<string>('');
  const [calling, setCalling] = useState(false);

  useEffect(() => {
    // 1. Try localStorage first
    try {
      const products = JSON.parse(localStorage.getItem('clawthon_products') || '{}');
      const product = products[id];
      if (product?.code) {
        setCode(product.code);
        setProductType(product.product_type || 'web_app');
        setProductName(product.name || `Product #${id}`);
        setLoading(false);
        return;
      }
    } catch { }

    // 2. Try backend API as fallback
    const apiUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').trim();
    fetch(`${apiUrl}/sandbox/product/${id}/preview`)
      .then(async (res) => {
        if (res.ok) {
          const html = await res.text();
          if (html && !html.includes('产品尚未开发') && !html.includes('"detail"')) {
            setCode(html);
            setProductType('web_app');
            setProductName(`Product #${id}`);
          }
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [id]);

  async function handleCall() {
    setCalling(true);
    setCallResult('');
    try {
      const apiUrl = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').trim();
      const res = await fetch(`${apiUrl}/sandbox/product/${id}/call`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: callInput,
      });
      const data = await res.json();
      setCallResult(JSON.stringify(data, null, 2));
    } catch (err: any) {
      setCallResult(`Error: ${err.message}`);
    } finally {
      setCalling(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50">
        <p className="text-gray-500">加载产品中...</p>
      </div>
    );
  }

  if (!code) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-50 gap-4">
        <p className="text-2xl">🚧 产品尚未开发</p>
        <p className="text-gray-500">项目 #{id} 的 Agent 还没有生成代码，请等待自治流产出新产品</p>
      </div>
    );
  }

  // Web app: render in iframe
  if (productType === 'web_app') {
    return (
      <div className="min-h-screen bg-gray-100">
        <div className="bg-white border-b px-4 py-2 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold text-gray-800">🚀 {productName}</span>
            <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded">Agent 开发的真实产品</span>
          </div>
          <span className="text-xs text-gray-400">Powered by Clawthon AI Agent</span>
        </div>
        <iframe
          srcDoc={code}
          className="w-full border-0"
          style={{ height: 'calc(100vh - 44px)' }}
          sandbox="allow-scripts allow-forms allow-modals"
          title={productName}
        />
      </div>
    );
  }

  // Skill / MCP: show code + call UI
  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="mx-auto max-w-3xl px-4">
        <h1 className="text-2xl font-bold mb-2">🔧 {productName}</h1>
        <p className="text-sm text-gray-500 mb-4">
          类型：{productType === 'agent_skill' ? 'Agent Skill' : 'MCP Service'} · 项目 #{id}
        </p>

        <div className="bg-gray-900 rounded-lg p-4 mb-6 text-sm text-green-400 font-mono overflow-x-auto max-h-80 overflow-y-auto">
          <pre>{code}</pre>
        </div>

        <div className="bg-white border rounded-lg p-4">
          <p className="font-medium mb-2">调用测试</p>
          <textarea
            value={callInput}
            onChange={(e) => setCallInput(e.target.value)}
            className="w-full border rounded p-2 font-mono text-sm mb-2"
            rows={4}
          />
          <button
            onClick={handleCall}
            disabled={calling}
            className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
          >
            {calling ? '调用中...' : '调用 Skill'}
          </button>
          {callResult && (
            <div className="mt-4 bg-gray-50 border rounded p-3 text-sm font-mono overflow-x-auto">
              <pre>{callResult}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
