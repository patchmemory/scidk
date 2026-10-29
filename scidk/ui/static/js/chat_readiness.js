(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  $('readiness-profile').onchange = () => {
    $('readiness-tool').replaceChildren(...($('readiness-profile').value === 'review' ?
      [new Option('Selected assertion', 'get_assertion')] :
      [new Option('System context', 'get_system_context'), new Option('Ontology context', 'get_ontology_context'), new Option('Accepted fact', 'explain_fact')]));
    $('readiness-id').value = ''; $('readiness-checks').replaceChildren();
  };
  $('readiness-form').onsubmit = async event => {
    event.preventDefault(); $('readiness-checks').replaceChildren(); $('readiness-status').textContent = 'Checking configuration and current permissions…';
    const body = {profile: $('readiness-profile').value}, id = $('readiness-id').value.trim(), tool = $('readiness-tool').value;
    if (id) body.context = {tool, arguments: tool === 'get_assertion' ? {assertion_id: id} : tool === 'explain_fact' ? {fact_id: id} : {entry_id: id}};
    try {
      const response = await fetch((window.SCIDK_BASE || '') + '/admin/chat-readiness', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      const data = await response.json();
      if (!response.ok) throw new Error('Readiness unavailable. Check the named administrator session and development flags.');
      for (const item of data.checks) {
        const li = document.createElement('li'); li.textContent = (item.ok ? 'Ready: ' : 'Action needed: ') + item.check + '. ' + item.remediation;
        $('readiness-checks').append(li);
      }
      $('readiness-status').textContent = (data.ready ? 'Configured for the selected bounded context. ' : 'Configuration or authorization is incomplete. ') + data.notice;
    } catch (error) { $('readiness-status').textContent = error.message; }
  };
})();
