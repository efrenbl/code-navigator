#!/usr/bin/env node
// Parse a Claude Code stream-json run log for the codenav A/B harness.
// Every number here comes from the trace itself — never from the agent's prose.
//   - system/init  -> which tools + MCP servers the arm actually had (isolation proof)
//   - tool_use     -> per-tool call counts (Read/Grep/Bash vs mcp__codenav__*)
//   - result       -> usage (tokens), duration_ms, num_turns
import { readFileSync } from 'fs';

const file = process.argv[2];
const lines = readFileSync(file, 'utf8').split('\n').filter(Boolean);

const toolCalls = [];
let result = null;
let initTools = null;
let initMcp = null;

for (const line of lines) {
  let ev;
  try { ev = JSON.parse(line); } catch { continue; }
  if (ev.type === 'system' && ev.subtype === 'init') {
    initTools = ev.tools || [];
    initMcp = ev.mcp_servers || [];
  }
  if (ev.type === 'assistant' && ev.message?.content) {
    for (const block of ev.message.content) {
      if (block.type === 'tool_use') {
        let detail = '';
        if (/codenav/.test(block.name)) {
          const inp = block.input || {};
          detail = ' ' + JSON.stringify(inp.query ?? inp.file_path ?? inp.path ?? '').slice(0, 50);
        } else if (block.name === 'Bash') detail = ' ' + (block.input?.command ?? '').slice(0, 50);
        else if (block.name === 'Read') detail = ' ' + (block.input?.file_path ?? '').split('/').slice(-1)[0];
        else if (block.name === 'Grep') detail = ' ' + (block.input?.pattern ?? '').slice(0, 40);
        toolCalls.push(`${block.name}${detail}`);
      }
    }
  }
  if (ev.type === 'result') result = ev;
}

const counts = {};
for (const tc of toolCalls) { const n = tc.split(' ')[0]; counts[n] = (counts[n] || 0) + 1; }
const codenavTools = (initTools || []).filter((t) => /codenav/.test(t));
const nativeSearch = (counts.Read || 0) + (counts.Grep || 0) + (counts.Glob || 0);

console.log(`\n=== ${file.split('/').pop()} ===`);
console.log(`isolation: mcp_servers=${JSON.stringify(initMcp?.map((m) => m.name) ?? [])} codenav_tools=${codenavTools.length}`);
console.log(`tool calls (${toolCalls.length}) by type: ${JSON.stringify(counts)}`);
console.log(`native search (Read+Grep+Glob): ${nativeSearch}`);
toolCalls.forEach((tc, i) => console.log(`  ${i + 1}. ${tc}`));

if (result) {
  const u = result.usage || {};
  const totalIn = (u.input_tokens || 0) + (u.cache_read_input_tokens || 0) + (u.cache_creation_input_tokens || 0);
  console.log(`\nresult: ${result.subtype} | duration ${(result.duration_ms / 1000).toFixed(0)}s | turns ${result.num_turns}`);
  console.log(`tokens: in=${totalIn} out=${u.output_tokens || 0} | cost $${(result.total_cost_usd || 0).toFixed(3)}`);
  // Machine-readable summary line for aggregation across cells.
  console.log(`METRIC ${JSON.stringify({
    file: file.split('/').pop(),
    calls: toolCalls.length,
    by_type: counts,
    native_search: nativeSearch,
    tokens_in: totalIn,
    tokens_out: u.output_tokens || 0,
    cost_usd: result.total_cost_usd || 0,
    duration_s: +(result.duration_ms / 1000).toFixed(1),
    turns: result.num_turns,
    subtype: result.subtype,
  })}`);
}
