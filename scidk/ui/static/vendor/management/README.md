# Maps dependencies

Vendored from the existing Maps CDN dependency versions for offline/same-origin loading.
Licenses are included. No visual baseline is approved by vendoring these files.

| File | Upstream URL | SHA-256 |
|---|---|---|
| `lodash.min.js` | https://unpkg.com/lodash@4.17.21/lodash.min.js | `a9705dfc47c0763380d851ab1801be6f76019f6b67e40e9b873f8b4a0603f7a9` |
| `edgehandles.js` | https://unpkg.com/cytoscape-edgehandles@4.0.1/cytoscape-edgehandles.js | `0f3cc29c8d7a0306ff7895fc34483e7a18d2047e4ce152782dc94f2da83a16ee` |
| `undo-redo.js` | https://unpkg.com/cytoscape-undo-redo@1.3.3/cytoscape-undo-redo.js | `2a2f4b54e0f0c24ed8c0aface99ce3f10dd3862026260ed6b5227b7e75f8d731` |
| `codemirror.min.js` | https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/codemirror.min.js | `458689ce1e2e10b9e363c4d6ef5e6edbfaf2fb42ccc38871c259a9092d75c7c6` |
| `codemirror.min.css` | https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/codemirror.min.css | `11077112ab6955d29fe41085c62365c7d4a2f00a570c7475e2aec2a8cbc85fc4` |
| `cypher.min.js` | https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/mode/cypher/cypher.min.js | `684c4eda91148c9d87f3148d2f7bb9ebe1b0ad90d9bce26ba5cd41b976edd51f` |
| `matchbrackets.min.js` | https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/addon/edit/matchbrackets.min.js | `f359c5f395a2a08191557d40b61ef8c3893803da9019171cc44b8d9c8c7d4a3a` |
| `closebrackets.min.js` | https://cdnjs.cloudflare.com/ajax/libs/codemirror/6.65.7/addon/edit/closebrackets.min.js | `df4a87dd3b175b509468755b74d06f0e82ff56f213f341f776c26ff0f0d27b37` |
| `LICENSE-lodash` | https://unpkg.com/lodash@4.17.21/LICENSE | `f71e8ed126b46346494aad5486874cd8f0aafe95092ed67d2e3cb6110f939abc` |
| `LICENSE-edgehandles` | https://unpkg.com/cytoscape-edgehandles@4.0.1/LICENSE | `63e7a59e9eee8fc982a9fdd41edfc20676c63313fe35ad98791221144994afcc` |
| `LICENSE-undo-redo` | https://unpkg.com/cytoscape-undo-redo@1.3.3/LICENSE.md | `c5f3475bb3fe3e9de7714776deac633ec7eb0f8198ddc3a4e67e902711eccea7` |
| `LICENSE-codemirror` | https://unpkg.com/codemirror@5.65.7/LICENSE | `a3f2fe2ac6b471aa80c737c5d283dd049bdc903a73835ee6d4d2cac02fdd53bf` |

cdnjs publishes the CodeMirror 5 bundle under its `6.65.7` asset path. The MIT license is from upstream CodeMirror 5.65.7.

`undo-redo.js` has trailing spaces removed; other assets retain upstream bytes.
