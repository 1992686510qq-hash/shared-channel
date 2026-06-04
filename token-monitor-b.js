#!/usr/bin/env node
/**
 * Token 监控系统 - B 部分
 * 功能：
 *   1. 读取 ~/.claude/.ccl-sessions.json 获取所有会话的 proxyPort
 *   2. 对每个活跃端口调用 /admin/status 接口
 *   3. 根据 baseUrl 判断 API 来源（小米/DeepSeek/智谱）
 *   4. 输出结果
 */

const fs = require('fs');
const path = require('path');
const http = require('http');

// ── 配置 ──────────────────────────────────────────────────────────────────────
const CCL_SESSIONS_FILE = path.join(
  process.env.HOME || process.env.USERPROFILE,
  '.claude',
  '.ccl-sessions.json'
);

const PROBE_TIMEOUT_MS = 3000;

// ── API 来源识别 ──────────────────────────────────────────────────────────────

/**
 * 根据 baseUrl 判断 API 来源类型
 * @param {string} baseUrl
 * @returns {{ type: string, label: string }}
 */
function identifyApiSource(baseUrl) {
  if (!baseUrl) return { type: 'unknown', label: '未知' };
  const url = baseUrl.toLowerCase();

  if (url.includes('xiaomimimo')) {
    // 区分小米国内/海外节点
    if (url.includes('token-plan-cn')) return { type: 'xiaomi-cn', label: '小米(国内)' };
    if (url.includes('token-plan-sgp')) return { type: 'xiaomi-sgp', label: '小米(新加坡)' };
    return { type: 'xiaomi', label: '小米' };
  }
  if (url.includes('deepseek'))    return { type: 'deepseek', label: 'DeepSeek' };
  if (url.includes('bigmodel'))    return { type: 'zhipu',    label: '智谱' };
  if (url.includes('openai'))      return { type: 'openai',   label: 'OpenAI' };
  if (url.includes('anthropic'))   return { type: 'anthropic', label: 'Anthropic' };

  return { type: 'other', label: `其他(${baseUrl})` };
}

// ── 探测端口 ──────────────────────────────────────────────────────────────────

/**
 * 调用 /admin/status 接口
 * @param {number} port
 * @returns {Promise<object|null>}
 */
function probePort(port) {
  return new Promise((resolve) => {
    const req = http.get(
      `http://127.0.0.1:${port}/admin/status`,
      { timeout: PROBE_TIMEOUT_MS },
      (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => {
          try {
            resolve(JSON.parse(data));
          } catch {
            resolve(null);
          }
        });
      }
    );
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
  });
}

// ── 读取配置文件获取 baseUrl ───────────────────────────────────────────────────

/**
 * 从 proxy 配置文件中读取 current provider 的 baseUrl
 * @param {string} configPath - 配置文件绝对路径
 * @param {string} currentKey - 当前 provider key (e.g. "setting-s3.json")
 * @returns {string|null}
 */
function getBaseUrlFromConfig(configPath, currentKey) {
  try {
    if (!fs.existsSync(configPath)) return null;
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    const provider = config.providers?.[currentKey];
    return provider?.baseUrl || null;
  } catch {
    return null;
  }
}

// ── 主流程 ────────────────────────────────────────────────────────────────────

async function main() {
  // 1. 读取 .ccl-sessions.json
  if (!fs.existsSync(CCL_SESSIONS_FILE)) {
    console.error('[TokenMonitor-B] .ccl-sessions.json 不存在');
    process.exit(1);
  }

  const sessions = JSON.parse(fs.readFileSync(CCL_SESSIONS_FILE, 'utf8'));
  const sessionsWithPort = sessions.filter((s) => s.proxyPort);

  console.log(`[TokenMonitor-B] 共 ${sessions.length} 个会话，${sessionsWithPort.length} 个有 proxyPort\n`);

  if (sessionsWithPort.length === 0) {
    console.log('[TokenMonitor-B] 无活跃端口，退出');
    process.exit(0);
  }

  // 2. 并发探测所有端口
  const probes = await Promise.all(
    sessionsWithPort.map(async (session) => {
      const port = session.proxyPort;
      const status = await probePort(port);
      return { session, port, status };
    })
  );

  // 3. 解析结果
  const results = probes.map(({ session, port, status }) => {
    const online = status !== null;

    // 从 /admin/status 响应中获取 config 路径和 current provider
    const configPath = status?.config || null;
    const currentKey = status?.current || null;

    // 读取配置文件获取 baseUrl
    let baseUrl = null;
    if (configPath && currentKey) {
      baseUrl = getBaseUrlFromConfig(configPath, currentKey);
    }

    // 判断 API 来源
    const source = identifyApiSource(baseUrl);

    return {
      port,
      uuid: session.uuid,
      sessionName: session.sessionName || '(unnamed)',
      project: session.project || 'unknown',
      online,
      currentProvider: currentKey,
      baseUrl: baseUrl || 'N/A',
      apiSource: source.type,
      apiLabel: source.label,
      configPath: configPath || 'N/A',
    };
  });

  // 4. 输出结果
  console.log('='.repeat(72));
  console.log('  Token 监控 - 代理端口状态 & API 来源');
  console.log('='.repeat(72));

  for (const r of results) {
    const statusIcon = r.online ? '[ONLINE] ' : '[OFFLINE]';
    console.log(`
  ${statusIcon} 端口 ${r.port}  |  会话: ${r.sessionName}
    UUID:    ${r.uuid}
    项目:    ${r.project}
    配置:    ${r.configPath}
    当前Provider: ${r.currentProvider || 'N/A'}
    BaseURL:     ${r.baseUrl}
    API 来源:    ${r.apiLabel} (${r.apiSource})
`);
  }

  // 汇总
  const online = results.filter((r) => r.online);
  const offline = results.filter((r) => !r.online);
  const sourceCounts = {};
  for (const r of online) {
    sourceCounts[r.apiLabel] = (sourceCounts[r.apiLabel] || 0) + 1;
  }

  console.log('-'.repeat(72));
  console.log(`  汇总: ${online.length} 在线 / ${offline.length} 离线 / ${results.length} 总计`);
  if (Object.keys(sourceCounts).length > 0) {
    const parts = Object.entries(sourceCounts).map(([k, v]) => `${k}:${v}`);
    console.log(`  在线来源分布: ${parts.join(', ')}`);
  }
  console.log('='.repeat(72));

  // 5. 输出 JSON 格式（供其他程序消费）
  const output = {
    timestamp: new Date().toISOString(),
    total: results.length,
    online: online.length,
    offline: offline.length,
    sourceDistribution: sourceCounts,
    proxies: results,
  };

  // 写入结果文件
  const outputPath = path.join(__dirname, 'token-monitor-result.json');
  fs.writeFileSync(outputPath, JSON.stringify(output, null, 2), 'utf8');
  console.log(`\n[TokenMonitor-B] 结果已写入: ${outputPath}`);
}

main().catch((err) => {
  console.error('[TokenMonitor-B] 执行失败:', err);
  process.exit(1);
});
