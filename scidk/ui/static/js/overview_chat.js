(function () {
  'use strict';
  const $ = id => document.getElementById(id), base = window.SCIDK_BASE || '';
  const params = new URLSearchParams(location.search);
  const domain = params.get('domain'), id = params.get('id');
  let selection = ['research', 'system', 'ontology'].includes(domain) && id && id.length <= 256 ? {domain, id} : null;
  if (selection) { $('overview-scope').querySelector('[value=selection]').disabled = false; $('overview-scope').value = 'selection'; }
  let version = 0;
  function clear() {
    version++; $('overview-answer').textContent = ''; $('overview-sources').textContent = '';
    $('overview-source-links').replaceChildren();
    ['overview-answer-heading', 'overview-source-heading', 'overview-source-details'].forEach(id => $(id).hidden = true);
  }
  $('overview-scope').onchange = () => { clear(); $('overview-consent').checked = false; };
  $('overview-question').oninput = clear;
  document.querySelectorAll('[data-question]').forEach(button => button.onclick = () => {
    clear(); $('overview-question').value = button.dataset.question;
    $('overview-scope').value = button.dataset.scope || 'accessible'; $('overview-consent').checked = false; $('overview-question').focus();
  });
  $('overview-chat').onsubmit = async event => {
    event.preventDefault(); clear(); const current = version;
    if (!$('overview-consent').checked) return;
    $('overview-send').disabled = true; $('overview-status').textContent = 'Finding matching sources and checking your permissions…';
    const body = {message: $('overview-question').value, scope: $('overview-scope').value, send_question: true};
    if (body.scope === 'selection') body.selection = selection;
    try {
      const response = await fetch(base + '/api/chat/overview', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      const data = await response.json();
      if (current !== version) return;
      if (!response.ok || data.status !== 'success') throw new Error(['error', 'refused'].includes(data.status) ? 'Knowledge access is unavailable. Ask an administrator to check source permissions and the approved provider.' : data.error || 'Knowledge is unavailable.');
      $('overview-answer').textContent = data.reply; $('overview-answer-heading').hidden = false;
      $('overview-sources').textContent = JSON.stringify(data.context, null, 2);
      $('overview-source-heading').hidden = false; $('overview-source-details').hidden = false;
      if (data.context.tool_calls) $('overview-source-details').open = true;
      for (const source of data.context.retrieved_sources || []) {
        const link = document.createElement('a'); link.className = 'source-link';
        link.textContent = source.title + ' · ' + (source.domain === 'research' ? 'Accepted, applied support' : 'Documentation & provenance');
        // Build same-origin links from authorized stable identifiers only.
        link.href = base + '/knowledge?' + new URLSearchParams({domain: source.domain, id: source.id});
        const article = document.createElement('article'); article.append(link);
        const facts = source.context.properties;
        if (facts) {
          const list = document.createElement('dl');
          for (const [key, value] of Object.entries(facts)) { const term = document.createElement('dt'), detail = document.createElement('dd'); term.textContent = key; detail.textContent = typeof value === 'object' ? JSON.stringify(value) : String(value); list.append(term, detail); }
          article.append(list);
        }
        const citations = source.context.support?.flatMap(s => s.citations || []) || source.context.context?.nodes?.flatMap(n => n.sources || []) || [];
        for (const citation of citations) { const line = document.createElement('p'); line.textContent = typeof citation === 'string' ? citation : citation.citation || citation.path || 'Authorized evidence; inspect source details'; article.append(line); }
        $('overview-source-links').append(article);
      }
      $('overview-status').textContent = data.notice;
    } catch (error) { if (current === version) $('overview-status').textContent = error.message; }
    finally { $('overview-send').disabled = false; }
  };
})();
