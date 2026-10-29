(function () {
  'use strict';
  const $ = id => document.getElementById(id), base = window.SCIDK_BASE || '';
  const params = new URLSearchParams(location.search);
  const state = {version: 0, selected: null, preview: null, offset: 0, next: null,
    context: params.get('id') || '', domain: params.get('domain') || ''};
  if (['research', 'system', 'ontology'].includes(state.domain)) $('rw-domain').value = state.domain;
  const status = message => { $('rw-status').textContent = message; };
  async function api(operation, body) {
    let response;
    try {
      response = await fetch(base + '/api/review/' + operation, {method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    } catch (_) { throw new Error('Connection unavailable. Retry when the server is reachable.'); }
    let data;
    try { data = await response.json(); } catch (_) { throw new Error('Review service unavailable. Retry or ask an administrator to check configuration.'); }
    if (!response.ok || data.status !== 'success') {
      if (response.status === 409) throw new Error('This item changed. Reload it and prepare a new decision.');
      throw new Error('Access unavailable for this operation. Check your named session, source and evidence grants, reviewer permission, and approved provider with an administrator.');
    }
    return data.result;
  }
  function clearDetail() {
    state.selected = null; state.preview = null;
    ['rw-summary', 'rw-claim', 'rw-evidence', 'rw-history-data', 'rw-conflicts', 'rw-answer', 'rw-chat-sources', 'rw-chat-status'].forEach(id => $(id).replaceChildren());
    $('rw-selection').textContent = 'Select an assertion to inspect its permitted claim and citations.';
    $('rw-decision').hidden = true; $('rw-confirm').checked = false; $('rw-rationale').value = '';
    $('rw-prepare').disabled = true; $('rw-history').disabled = true;
    if ($('rw-send')) $('rw-send').disabled = true;
    if ($('rw-send-consent')) $('rw-send-consent').checked = false;
  }
  function updateReturn(item) {
    const claim = item.claim;
    const ref = claim.entity_ref || claim.target_ref || claim.subject_ref || item.fact_id;
    $('rw-return').href = base + '/knowledge?' + new URLSearchParams({domain: claim.domain, id: ref});
    const query = new URLSearchParams({domain: claim.domain, id: item.assertion_id});
    history.replaceState(null, '', location.pathname + '?' + query);
  }
  async function select(id, focus = true) {
    const version = ++state.version; clearDetail(); status('Loading authorized assertion and citations…');
    try {
      const item = await api('inspect', {id});
      if (version !== state.version) return;
      state.selected = item;
      $('rw-selection').textContent = item.assertion_id;
      const values = {'Curation status': item.curation_status, 'Epistemic status': item.claim.epistemic_status,
        'Fact ID': item.fact_id, 'Domain / kind': item.claim.domain + ' / ' + item.claim.target_kind,
        'Ontology version': item.claim.ontology_version, 'Source Resource': item.source_scope.resource_id,
        'Decision revision': String(item.revision), 'Current rationale': item.rationale || 'No human decision recorded'};
      for (const [label, value] of Object.entries(values)) {
        const term = document.createElement('dt'), definition = document.createElement('dd');
        term.textContent = label; definition.textContent = value; $('rw-summary').append(term, definition);
      }
      $('rw-claim').textContent = JSON.stringify(item.claim, null, 2);
      for (const source of item.evidence) {
        const citation = document.createElement('p');
        citation.textContent = source.citation + ' — version ' + source.version + '; accessed ' + source.accessed_at + '; ' + source.evidence_id;
        $('rw-evidence').append(citation);
      }
      $('rw-prepare').disabled = false; $('rw-history').disabled = false;
      if ($('rw-send')) $('rw-send').disabled = false;
      document.querySelectorAll('#rw-queue button').forEach(button => {
        button.setAttribute('aria-current', String(button.dataset.id === id));
        if (button.dataset.id === id) button.textContent = item.claim.target_kind + ' · ' + item.curation_status + ' · ' + item.claim.epistemic_status + '\n' + id;
      });
      updateReturn(item); status('Authorized assertion loaded. Prepare a decision only after examining its evidence.');
      if (focus) $('rw-detail-heading').focus();
    } catch (error) { if (version === state.version) { clearDetail(); status(error.message); } }
  }
  async function queue(offset = 0) {
    const version = ++state.version; clearDetail(); $('rw-queue').replaceChildren();
    $('rw-queue').setAttribute('aria-busy', 'true'); $('rw-next').hidden = true;
    $('rw-clear-context').hidden = !state.context; status('Loading permitted assertions…');
    try {
      const result = await api('queue', {kind: $('rw-kind').value, domain: $('rw-domain').value,
        status: $('rw-filter-status').value, source: $('rw-source').value.trim(), offset, context_id: state.context});
      if (version !== state.version) return;
      state.offset = offset; state.next = result.next_offset;
      for (const item of result.items) {
        const button = document.createElement('button'); button.dataset.id = item.assertion_id;
        button.textContent = item.claim.target_kind + ' · ' + item.curation_status + ' · ' + item.claim.epistemic_status + '\n' + item.assertion_id;
        button.onclick = () => select(item.assertion_id); $('rw-queue').append(button);
      }
      $('rw-next').hidden = state.next === null;
      status(result.items.length ? 'Permitted assertions loaded. Select an item to examine its evidence.' :
        'No permitted assertions match these filters. Clear filters or ask an administrator about source/evidence access and curation setup. This is not a global record count.');
      if (state.context && result.items.length) {
        const exact = result.items.find(item => item.assertion_id === state.context);
        if (exact || result.items.length === 1) await select((exact || result.items[0]).assertion_id, false);
      }
    } catch (error) { if (version === state.version) status(error.message); }
    finally { $('rw-queue').setAttribute('aria-busy', 'false'); }
  }
  $('rw-filters').onsubmit = event => { event.preventDefault(); queue(); };
  $('rw-next').onclick = () => { if (state.next !== null) queue(state.next); };
  $('rw-clear-context').onclick = () => { state.context = ''; history.replaceState(null, '', location.pathname); queue(); };
  $('rw-history').onclick = async () => {
    if (!state.selected) return;
    const version = state.version, id = state.selected.assertion_id;
    $('rw-history-data').textContent = 'Checking history permission…';
    try {
      const result = await api('inspect', {id, history: true});
      if (version === state.version) $('rw-history-data').textContent = JSON.stringify(result.decision_history, null, 2);
    } catch (error) { if (version === state.version) $('rw-history-data').textContent = error.message; }
  };
  $('rw-prepare').onclick = async () => {
    if (!state.selected) return;
    const version = state.version, id = state.selected.assertion_id;
    state.preview = null; $('rw-decision').hidden = true; status('Checking current reviewer permission, conflicts and revision…');
    try {
      const result = await api('preview', {id});
      if (version !== state.version) return;
      state.preview = result;
      $('rw-conflicts').textContent = result.conflict_ids.length ? 'Authorized accepted conflicts: ' + result.conflict_ids.join(', ') : 'No accepted property conflict in this preview.';
      $('rw-action').value = state.selected.curation_status === 'accepted' ? 'supersede' : 'accept';
      $('rw-action').onchange(); $('rw-confirm').checked = false; $('rw-decision').hidden = false;
      status(result.notice); $('rw-action').focus();
    } catch (error) { if (version === state.version) status(error.message); }
  };
  $('rw-action').onchange = () => {
    const replacement = $('rw-action').value === 'supersede';
    $('rw-replacement-label').hidden = !replacement; $('rw-replacement').required = replacement;
  };
  $('rw-cancel').onclick = () => { state.preview = null; $('rw-decision').hidden = true; $('rw-confirm').checked = false; $('rw-prepare').focus(); };
  $('rw-decision').onsubmit = async event => {
    event.preventDefault();
    if (!state.selected || !state.preview || !$('rw-confirm').checked) return;
    const version = state.version, id = state.selected.assertion_id;
    const body = {id, action: $('rw-action').value, rationale: $('rw-rationale').value,
      expected_revision: state.preview.expected_revision, preview_digest: state.preview.preview_digest, confirm: true};
    if (body.action === 'supersede') body.superseded_by = $('rw-replacement').value.trim();
    $('rw-decide').disabled = true;
    try {
      const result = await api('decide', body);
      if (version !== state.version) return;
      await select(id, false);
      status('Recorded ' + result.curation_status + ' decision. Graph materialization is pending; no graph write was performed.');
    } catch (error) {
      if (version === state.version) { state.preview = null; $('rw-decision').hidden = true; $('rw-confirm').checked = false; status(error.message); }
    } finally { $('rw-decide').disabled = false; }
  };
  if ($('rw-chat')) $('rw-chat').onsubmit = async event => {
    event.preventDefault(); if (!state.selected || !$('rw-send-consent').checked) return;
    const version = state.version;
    $('rw-answer').textContent = ''; $('rw-chat-sources').textContent = ''; $('rw-send').disabled = true;
    $('rw-chat-status').textContent = 'Checking current assertion support and provider approval…';
    try {
      const result = await api('assistant', {id: state.selected.assertion_id, message: $('rw-question').value, send_question: true});
      if (version !== state.version) return;
      $('rw-answer').textContent = result.reply; $('rw-chat-sources').textContent = JSON.stringify(result.context, null, 2);
      $('rw-chat-status').textContent = result.notice;
    } catch (error) { if (version === state.version) $('rw-chat-status').textContent = error.message; }
    finally { if (state.selected) $('rw-send').disabled = false; }
  };
  $('rw-proposal').onsubmit = async event => {
    event.preventDefault(); if (!$('rw-proposal-consent').checked) return;
    $('rw-submit-proposal').disabled = true; $('rw-proposal-status').textContent = 'Checking scoped proposal permission…';
    try {
      let assertion;
      try { assertion = JSON.parse($('rw-proposal-json').value); } catch (_) { throw new Error('Enter a valid JSON assertion.'); }
      const result = await api('propose', {assertion, caller_key: $('rw-caller-key').value, confirm: true});
      $('rw-proposal-status').textContent = 'Proposal recorded: ' + result.assertion_id + '. No acceptance or graph application.';
      $('rw-proposal-consent').checked = false;
    } catch (error) { $('rw-proposal-status').textContent = error.message; }
    finally { $('rw-submit-proposal').disabled = false; }
  };
  queue();
})();
