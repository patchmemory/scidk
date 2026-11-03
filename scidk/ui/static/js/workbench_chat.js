// Shared Chat workbench: the one explicit-Ask request. Loaded only when the server says Chat is ready.
// Sends {message, send_question: true} to the governed endpoint when the person presses Ask; renders the answer as text.
// No storage, no history, no credentials in the browser; nothing is sent without the cw:ask event from an Ask click.
(function () {
  var shell = document.getElementById('guidance-shell');
  var input = document.getElementById('guidance-input');
  var list = document.getElementById('guidance-messages');
  var button = document.getElementById('guidance-send');
  if (!shell || !input || !list || !button || shell.getAttribute('data-provider-state') !== 'configured') return;
  function add(kind, text, testid) {
    var el = document.createElement('div');
    el.className = 'gd-msg ' + kind;
    if (testid) el.setAttribute('data-testid', testid);
    el.textContent = text;
    list.appendChild(el);
    list.scrollTop = list.scrollHeight;
    return el;
  }
  shell.addEventListener('cw:ask', function (event) {
    event.preventDefault();
    var text = String((event.detail && event.detail.text) || '');
    shell.setAttribute('data-busy', 'true');
    button.disabled = true;
    var pending = add('system', 'Waiting for the AI provider\u2026', 'guidance-pending');
    function done() {
      shell.removeAttribute('data-busy');
      button.disabled = false;
      if (pending.parentNode) pending.parentNode.removeChild(pending);
      input.focus();
    }
    function failed(message) {
      add('notice', message || 'Chat could not answer. Your message was not answered.', 'guidance-error-notice');
      if (!input.value) input.value = text;
    }
    fetch(shell.getAttribute('data-send-url'), {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: text, send_question: true})
    }).then(function (response) {
      return response.json().then(function (data) { return data; }, function () { return {}; });
    }).then(function (data) {
      if (data && data.status === 'success' && typeof data.reply === 'string') {
        add('assistant', data.reply, 'guidance-assistant-message');
        if (typeof data.notice === 'string') add('notice', data.notice, 'guidance-answer-notice');
      } else {
        failed(data && typeof data.error === 'string' ? data.error : '');
      }
      done();
    }, function () { failed("Couldn't reach SciDK. Try again."); done(); });
  });
})();
