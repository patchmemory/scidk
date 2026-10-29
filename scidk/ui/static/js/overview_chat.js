(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  $('overview-chat').onsubmit = async event => {
    event.preventDefault(); $('overview-send').disabled = true;
    $('overview-status').textContent = 'Checking sources and preparing an answer…';
    $('overview-answer').textContent = ''; $('overview-sources').textContent = '';
    const tool = $('overview-context-type').value;
    const args = tool === 'explain_fact' ? {fact_id: $('overview-context-id').value} : {entry_id: $('overview-context-id').value};
    try {
      const response = await fetch((window.SCIDK_BASE || '') + '/api/chat/overview', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: $('overview-question').value,
          context: {tool, arguments: args}, send_question: $('overview-consent').checked})
      });
      const data = await response.json();
      if (!response.ok || data.status !== 'success') throw new Error(data.error || 'Overview is unavailable.');
      $('overview-answer').textContent = data.reply;
      $('overview-sources').textContent = JSON.stringify(data.context, null, 2);
      $('overview-status').textContent = data.notice;
    } catch (error) { $('overview-status').textContent = error.message; }
    finally { $('overview-send').disabled = false; }
  };
})();
