/**
 * Clawthon 前端全量数据导出脚本 v2
 * ===================================
 * 直接从 localStorage 提取全部 50 个项目（不走 API，不受容器隔离影响）
 *
 * 步骤：
 *   1. 打开 https://clawthon-towow.vercel.app 并确保已登录
 *   2. F12 -> Console
 *   3. 粘贴本脚本全文 -> 回车
 *   4. 自动弹出 JSON 下载
 */

(async () => {
  console.log('🦞 Clawthon v2 全量数据导出（从 localStorage 直接读取）...');

  const result = {
    exported_at: new Date().toISOString(),
    source: 'localStorage',
    projects: [],
    products: [],
    events: [],
    agents: [],
    dashboard: null,
    transactions: [],
    investments: [],
  };

  // ========== 1. 从 localStorage 读取项目（核心数据源） ==========
  console.log('[1/4] 从 localStorage 读取项目数据...');
  try {
    const raw = localStorage.getItem('clawthon_workbench_projects');
    if (raw) {
      const projects = JSON.parse(raw);
      if (Array.isArray(projects)) {
        result.projects = projects;
        console.log(`   ✅ ${projects.length} 个项目`);
      }
    }
  } catch (e) {
    console.warn('   ⚠️ localStorage 读取失败:', e.message);
  }

  if (result.projects.length === 0) {
    console.error('❌ localStorage 中没有项目数据。请确保在 Agent 工作台页面已加载过项目。');
    console.log('   提示：先打开 Agent 工作台页面，等项目列表加载完成后再运行此脚本。');
    return;
  }

  // ========== 2. 通过 API 补充数据（产品/Agent/Dashboard） ==========
  const API = (() => {
    // 从 Next.js 配置中获取
    try {
      const scripts = document.querySelectorAll('script[id="__NEXT_DATA__"]');
      if (scripts.length > 0) {
        const nd = JSON.parse(scripts[0].textContent);
        if (nd?.runtimeConfig?.NEXT_PUBLIC_API_URL) return nd.runtimeConfig.NEXT_PUBLIC_API_URL;
      }
    } catch {}
    return 'https://clawthon-towow-api.vercel.app';
  })();

  const TOKEN = localStorage.getItem('clawthon_token');
  const headers = TOKEN ? { 'Authorization': `Bearer ${TOKEN}`, 'Content-Type': 'application/json' } : {};

  console.log('[2/4] 补充 API 数据...');

  // Products
  try {
    const resp = await fetch(`${API}/sandbox/products`);
    if (resp.ok) {
      result.products = await resp.json();
      console.log(`   Products: ${result.products.length}`);
    }
  } catch {}

  // Download product HTML
  for (const p of result.products) {
    if (p.preview_url) {
      try {
        const resp = await fetch(`${API}${p.preview_url}`);
        if (resp.ok) p._html_code = await resp.text();
      } catch {}
    }
  }

  // Agents
  if (TOKEN) {
    try {
      const resp = await fetch(`${API}/plaza/agents`, { headers });
      if (resp.ok) result.agents = await resp.json();
      console.log(`   Agents: ${result.agents.length}`);
    } catch {}

    // Dashboard
    try {
      const resp = await fetch(`${API}/transactions/dashboard`, { headers });
      if (resp.ok) result.dashboard = await resp.json();
      console.log('   Dashboard: OK');
    } catch {}

    // Transactions
    try {
      const resp = await fetch(`${API}/transactions/my?limit=500`, { headers });
      if (resp.ok) result.transactions = await resp.json();
      console.log(`   Transactions: ${result.transactions.length}`);
    } catch {}

    // Investments
    try {
      const resp = await fetch(`${API}/transactions/investments/my`, { headers });
      if (resp.ok) result.investments = await resp.json();
      console.log(`   Investments: ${result.investments.length}`);
    } catch {}
  }

  // ========== 3. 统计 ==========
  console.log('\n[3/4] 📊 统计:');
  let totalPRDs = 0, totalMsgs = 0, totalSummaries = 0, totalDeploys = 0;
  for (const p of result.projects) {
    for (const evt of (p.progress || [])) {
      if (evt.event_type === 'prd_generated') totalPRDs++;
      if (evt.event_type === 'message') totalMsgs++;
      if (evt.event_type === 'summary') totalSummaries++;
      if (evt.event_type === 'product_deployed') totalDeploys++;
    }
  }
  console.log(`   项目:     ${result.projects.length}`);
  console.log(`   产品:     ${result.products.length}`);
  console.log(`   PRD文档:  ${totalPRDs}`);
  console.log(`   讨论消息: ${totalMsgs}`);
  console.log(`   摘要:     ${totalSummaries}`);
  console.log(`   产品部署: ${totalDeploys}`);

  // ========== 4. 下载 ==========
  console.log('\n[4/4] 生成下载文件...');
  const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `clawthon_full_export_${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);

  console.log(`\n✅ 导出完成! 文件: ${a.download}`);
  console.log(`   ${result.projects.length} 个项目, ${totalPRDs} 份 PRD, ${totalMsgs} 条讨论`);
  console.log('   下载后运行: python import_browser_export.py <文件路径>');

  window.__clawthon_export = result;
})();
