/**
 * Authoritative per-tab canvas state for the Maps workspace.
 *
 * Why this exists: a map tab's canvas used to be "whatever the last writer drew",
 * and several asynchronous paths could write it - the default Schema fetch (started
 * by the mode control, including the synthetic change event a saved-map load
 * dispatches), the auto-run of a loaded map's query, and a query response that
 * arrives after the user has moved on. A slow Schema response landing after a loaded
 * map or query result replaced it with the default Schema graph.
 *
 * Ownership rule: every user-initiated *replacement* render calls ``begin`` which
 * increments the tab's ``generation``. Every asynchronous continuation captures the
 * generation it was started under and must pass ``isCurrent`` before it touches the
 * canvas, the mode control or the stored state. A stale continuation discards its
 * result. Default Schema content may only be requested through ``mayRenderDefault``,
 * which is true solely for a genuinely new, never-rendered tab.
 *
 * Pure logic, no DOM: the browser binds it to Cytoscape/radios, and
 * tests/test_map_tab_state.py runs this same file under Node.
 */
(function (root) {
  'use strict';

  var MODES = ['schema', 'instance', 'hybrid'];

  function newState(tabId) {
    return {
      tabId: tabId,
      savedMapId: null,        // saved-map identity, when one was loaded
      savedMapName: null,
      queryText: null,         // query that produced the rendered result
      queryId: null,           // library query identity, when known
      renderKind: 'empty',     // empty | default-schema | saved-map | query-result | canvas
      renderedMode: 'schema',  // what the Schema/Instance control must show
      renderedData: null,      // result rows / schema payload behind the canvas
      elements: null,          // serialised canvas elements (restored if the canvas is lost)
      positions: null,         // {id: {x, y}} captured when the tab is left
      connection: null,        // connection the content was produced against
      generation: 0,           // bumped by every user-initiated replacement
      hasRender: false
    };
  }

  function createStore() {
    var states = {};

    function get(tabId) {
      if (!states[tabId]) states[tabId] = newState(tabId);
      return states[tabId];
    }

    // Start a user-initiated replacement. Returns the token async work must hold.
    function begin(tabId, patch) {
      var s = get(tabId);
      s.generation += 1;
      apply(s, patch);
      return s.generation;
    }

    function isCurrent(tabId, generation) {
      return !!states[tabId] && states[tabId].generation === generation;
    }

    // Apply a patch only if the caller's generation is still current.
    function commit(tabId, generation, patch) {
      if (!isCurrent(tabId, generation)) return false;
      apply(states[tabId], patch);
      return true;
    }

    function apply(s, patch) {
      if (!patch) return;
      Object.keys(patch).forEach(function (k) {
        if (k === 'generation' || k === 'tabId') return;
        if (k === 'renderedMode' && MODES.indexOf(patch[k]) < 0) return;
        s[k] = patch[k];
      });
    }

    // Default Schema content is only legitimate for a tab that has never held
    // a saved map, a query result, or any other render, and has not been replaced.
    function mayRenderDefault(tabId) {
      var s = get(tabId);
      return !s.hasRender && s.generation === 0 &&
        !s.savedMapId && !s.queryText && s.renderKind === 'empty';
    }

    // Run an async producer under the generation captured NOW. ``produce`` returns
    // a promise of data; ``render`` is only called if the generation is still
    // current when it resolves. Resolves to true when rendered, false if discarded.
    function runGuarded(tabId, generation, produce, render) {
      return Promise.resolve().then(produce).then(function (data) {
        if (!isCurrent(tabId, generation)) return false;
        render(data, generation);
        return true;
      });
    }

    function drop(tabId) { delete states[tabId]; }

    return {
      get: get, begin: begin, isCurrent: isCurrent, commit: commit,
      mayRenderDefault: mayRenderDefault, runGuarded: runGuarded, drop: drop,
      all: function () { return states; }
    };
  }

  var api = { createStore: createStore, MODES: MODES };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.MapTabState = api;
  if (!root.mapTabStore) root.mapTabStore = createStore();
})(typeof window !== 'undefined' ? window : this);
