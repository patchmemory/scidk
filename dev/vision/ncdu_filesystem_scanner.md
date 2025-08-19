# SciDK GDU-Powered Filesystem Scanner: Standards-Based Directory Analysis

## Vision: Reliable Filesystem Analysis with ncdu

Instead of building custom directory scanning, SciDK integrates **ncdu** as the primary filesystem analysis tool, with support for **gdu** output when available. This follows our core principle: **use existing tools, enhance with intelligence**.

**Priority: Reliability over performance optimization.**

```
┌─────────────────────────────────────────────────────────────┐
│                    Filesystem Analysis                      │
│                                                             │
│  ncdu (Primary) ────────► JSON Output ────────► Neo4j      │
│  (Reliable & Stable)      (Standard Format)    (Intelligence)│
│                                                             │
│  gdu (Optional) ─────────► Import Compatible               │
│  (When Available)                                           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                Research Object Creation                     │
│  • Smart directory selection                               │
│  • Automated metadata discovery                            │
│  • Size-aware organization                                 │
│  • Duplicate detection                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Why ncdu as Primary Tool

### **Reliability & Stability**
- **ncdu**: 15+ years of development, battle-tested across environments
- **Consistent behavior**: Works identically on HDD, SSD, network storage, low memory
- **Wide availability**: Pre-installed on most Linux systems
- **Predictable failure modes**: Simple error handling and debugging

### **JSON Output Integration**
```bash
# ncdu provides reliable JSON export
ncdu -o scan_results.json /data/research

# Import existing gdu scans when available
# (gdu JSON format is compatible with processing)
```

### **Research-Appropriate Performance**
- Scanning 500GB in ~5 minutes is fast enough for research workflows
- Users spend hours analyzing results, not minutes scanning
- Reliability more valuable than 8x speed improvement
- Consistent performance across different computing environments

---

## User Experience: Intelligent Directory Analysis

### **Main Scanner Interface**
```html
<!DOCTYPE html>
<html>
<head>
    <title>SciDK - Filesystem Scanner</title>
    <link rel="stylesheet" href="/static/css/filesystem-scanner.css">
</head>
<body>
    <div class="scanner-interface">
        
        <!-- Top Panel: Scan Controls -->
        <div class="scan-controls">
            <div class="scan-input">
                <h2>🔍 Directory Analysis</h2>
                <div class="input-group">
                    <input type="text" id="scan-path" placeholder="/data/research" 
                           value="/home/user/research_data">
                    <button class="btn-primary" onclick="startScan()">
                        📊 Scan with gdu
                    </button>
                    <button class="btn-secondary" onclick="importScan()">
                        📥 Import Existing Scan
                    </button>
                </div>
                
                <div class="scan-options">
                    <label>
                        <input type="checkbox" id="include-hidden" checked>
                        Include hidden files/directories
                    </label>
                    <label>
                        <input type="checkbox" id="follow-symlinks">
                        Follow symbolic links
                    </label>
                    <label>
                        <input type="checkbox" id="cross-filesystems">
                        Cross filesystem boundaries
                    </label>
                </div>
            </div>
            
            <!-- Scan Progress -->
            <div class="scan-progress hidden" id="scan-progress">
                <div class="progress-info">
                    <span id="scan-status">Scanning directories...</span>
                    <span id="scan-stats">0 directories, 0 files processed</span>
                </div>
                <div class="progress-bar">
                    <div class="progress-fill" id="progress-fill"></div>
                </div>
                <button class="btn-cancel" onclick="cancelScan()">Cancel</button>
            </div>
        </div>
        
        <!-- Main Content: Split View -->
        <div class="scanner-content">
            
            <!-- Left Panel: Directory Tree -->
            <div class="directory-tree-panel">
                <div class="panel-header">
                    <h3>📁 Directory Structure</h3>
                    <div class="tree-controls">
                        <button onclick="expandAll()">⊞ Expand All</button>
                        <button onclick="collapseAll()">⊟ Collapse All</button>
                        <select id="sort-by">
                            <option value="size">Sort by Size</option>
                            <option value="name">Sort by Name</option>
                            <option value="date">Sort by Date</option>
                            <option value="count">Sort by File Count</option>
                        </select>
                    </div>
                </div>
                
                <div class="directory-tree" id="directory-tree">
                    <!-- Tree structure populated by JavaScript -->
                    <div class="tree-item expanded" data-path="/home/user/research_data">
                        <div class="tree-node" onclick="toggleNode(this)">
                            <span class="expand-icon">▼</span>
                            <span class="folder-icon">📁</span>
                            <span class="folder-name">research_data</span>
                            <span class="folder-size">487 GB</span>
                            <span class="folder-count">2,847 files</span>
                            <div class="folder-actions">
                                <button onclick="createROFromDirectory('/home/user/research_data')" 
                                        title="Create Research Object">🔬</button>
                                <button onclick="analyzeDirectory('/home/user/research_data')"
                                        title="Analyze Contents">🔍</button>
                            </div>
                        </div>
                        
                        <div class="tree-children">
                            <div class="tree-item" data-path="/home/user/research_data/microscopy">
                                <div class="tree-node" onclick="toggleNode(this)">
                                    <span class="expand-icon">▶</span>
                                    <span class="folder-icon">🔬</span>
                                    <span class="folder-name">microscopy</span>
                                    <span class="folder-size">245 GB</span>
                                    <span class="folder-count">1,234 files</span>
                                    <div class="folder-actions">
                                        <button onclick="createROFromDirectory('/home/user/research_data/microscopy')">🔬</button>
                                        <button onclick="analyzeDirectory('/home/user/research_data/microscopy')">🔍</button>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="tree-item" data-path="/home/user/research_data/genomics">
                                <div class="tree-node" onclick="toggleNode(this)">
                                    <span class="expand-icon">▶</span>
                                    <span class="folder-icon">🧬</span>
                                    <span class="folder-name">genomics</span>
                                    <span class="folder-size">178 GB</span>
                                    <span class="folder-count">567 files</span>
                                    <div class="folder-actions">
                                        <button onclick="createROFromDirectory('/home/user/research_data/genomics')">🔬</button>
                                        <button onclick="analyzeDirectory('/home/user/research_data/genomics')">🔍</button>
                                    </div>
                                </div>
                            </div>
                            
                            <div class="tree-item" data-path="/home/user/research_data/analysis">
                                <div class="tree-node" onclick="toggleNode(this)">
                                    <span class="expand-icon">▶</span>
                                    <span class="folder-icon">📊</span>
                                    <span class="folder-name">analysis</span>
                                    <span class="folder-size">64 GB</span>
                                    <span class="folder-count">1,046 files</span>
                                    <div class="folder-actions">
                                        <button onclick="createROFromDirectory('/home/user/research_data/analysis')">🔬</button>
                                        <button onclick="analyzeDirectory('/home/user/research_data/analysis')">🔍</button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Right Panel: Analysis & Intelligence -->
            <div class="analysis-panel">
                <div class="panel-tabs">
                    <button class="tab active" data-tab="overview">📊 Overview</button>
                    <button class="tab" data-tab="suggestions">💡 Smart Suggestions</button>
                    <button class="tab" data-tab="duplicates">👥 Duplicates</button>
                    <button class="tab" data-tab="export">📤 Export</button>
                </div>
                
                <!-- Overview Tab -->
                <div class="tab-content active" id="overview-tab">
                    <div class="scan-summary">
                        <h3>Scan Summary</h3>
                        <div class="summary-stats">
                            <div class="stat-item">
                                <div class="stat-value">487 GB</div>
                                <div class="stat-label">Total Size</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-value">2,847</div>
                                <div class="stat-label">Files</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-value">342</div>
                                <div class="stat-label">Directories</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-value">15</div>
                                <div class="stat-label">File Types</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="size-visualization">
                        <h4>Directory Sizes</h4>
                        <div class="size-chart" id="size-chart">
                            <!-- Interactive treemap/bar chart -->
                        </div>
                    </div>
                    
                    <div class="file-type-analysis">
                        <h4>File Type Distribution</h4>
                        <div class="file-types">
                            <div class="file-type-item">
                                <span class="type-icon">🔬</span>
                                <span class="type-name">TIFF Images</span>
                                <span class="type-size">245 GB</span>
                                <span class="type-count">1,234 files</span>
                                <div class="type-bar">
                                    <div class="type-fill" style="width: 50.3%"></div>
                                </div>
                            </div>
                            <div class="file-type-item">
                                <span class="type-icon">🧬</span>
                                <span class="type-name">FASTQ Files</span>
                                <span class="type-size">178 GB</span>
                                <span class="type-count">567 files</span>
                                <div class="type-bar">
                                    <div class="type-fill" style="width: 36.6%"></div>
                                </div>
                            </div>
                            <div class="file-type-item">
                                <span class="type-icon">📊</span>
                                <span class="type-name">CSV Data</span>
                                <span class="type-size">32 GB</span>
                                <span class="type-count">456 files</span>
                                <div class="type-bar">
                                    <div class="type-fill" style="width: 6.6%"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Smart Suggestions Tab -->
                <div class="tab-content" id="suggestions-tab">
                    <div class="suggestions-list">
                        <h3>💡 Research Object Suggestions</h3>
                        
                        <div class="suggestion-item high-priority">
                            <div class="suggestion-header">
                                <h4>🔬 Microscopy Research Object</h4>
                                <span class="confidence">95% confidence</span>
                            </div>
                            <p>Found cohesive microscopy dataset in /microscopy/</p>
                            <div class="suggestion-details">
                                <ul>
                                    <li>1,234 TIFF images (245 GB)</li>
                                    <li>Consistent naming pattern: sample_XXX_YYY.tiff</li>
                                    <li>Related metadata files present</li>
                                    <li>Time series: 2024-06-01 to 2024-08-15</li>
                                </ul>
                            </div>
                            <div class="suggestion-actions">
                                <button class="btn-primary" onclick="createROFromSuggestion('microscopy')">
                                    🔬 Create Research Object
                                </button>
                                <button class="btn-secondary" onclick="previewSuggestion('microscopy')">
                                    👁️ Preview
                                </button>
                            </div>
                        </div>
                        
                        <div class="suggestion-item medium-priority">
                            <div class="suggestion-header">
                                <h4>🧬 Genomics Pipeline</h4>
                                <span class="confidence">87% confidence</span>
                            </div>
                            <p>Complete bioinformatics workflow detected</p>
                            <div class="suggestion-details">
                                <ul>
                                    <li>Raw FASTQ files (178 GB)</li>
                                    <li>Analysis scripts (.py, .R, .sh)</li>
                                    <li>Results and intermediate files</li>
                                    <li>README.md documentation present</li>
                                </ul>
                            </div>
                            <div class="suggestion-actions">
                                <button class="btn-primary" onclick="createROFromSuggestion('genomics')">
                                    🔬 Create Research Object
                                </button>
                                <button class="btn-secondary" onclick="previewSuggestion('genomics')">
                                    👁️ Preview
                                </button>
                            </div>
                        </div>
                        
                        <div class="suggestion-item low-priority">
                            <div class="suggestion-header">
                                <h4>📁 Orphaned Analysis Files</h4>
                                <span class="confidence">45% confidence</span>
                            </div>
                            <p>Found 23 analysis files that might belong to existing research objects</p>
                            <div class="suggestion-actions">
                                <button class="btn-secondary" onclick="reviewOrphanedFiles()">
                                    🔍 Review Files
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Duplicates Tab -->
                <div class="tab-content" id="duplicates-tab">
                    <div class="duplicates-analysis">
                        <h3>👥 Duplicate Detection</h3>
                        <div class="duplicates-summary">
                            <div class="stat-item">
                                <div class="stat-value">12</div>
                                <div class="stat-label">Duplicate Groups</div>
                            </div>
                            <div class="stat-item">
                                <div class="stat-value">45 GB</div>
                                <div class="stat-label">Wasted Space</div>
                            </div>
                        </div>
                        
                        <div class="duplicate-groups">
                            <div class="duplicate-group">
                                <div class="group-header">
                                    <h4>📊 analysis_results.csv</h4>
                                    <span class="group-size">3 copies, 450 MB total</span>
                                </div>
                                <div class="duplicate-files">
                                    <div class="duplicate-file">
                                        <span class="file-path">/research_data/analysis/results.csv</span>
                                        <span class="file-date">2024-08-15</span>
                                        <button onclick="markAsOriginal(this)">✓ Keep</button>
                                    </div>
                                    <div class="duplicate-file">
                                        <span class="file-path">/research_data/backup/results.csv</span>
                                        <span class="file-date">2024-08-15</span>
                                        <button onclick="markForDeletion(this)">✗ Delete</button>
                                    </div>
                                    <div class="duplicate-file">
                                        <span class="file-path">/temp/analysis_results_copy.csv</span>
                                        <span class="file-date">2024-08-14</span>
                                        <button onclick="markForDeletion(this)">✗ Delete</button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Export Tab -->
                <div class="tab-content" id="export-tab">
                    <div class="export-options">
                        <h3>📤 Export Scan Results</h3>
                        
                        <div class="export-format">
                            <h4>gdu Format</h4>
                            <p>Native gdu JSON format for sharing or archiving</p>
                            <button class="btn-primary" onclick="exportScan('gdu')">
                                📊 Export as gdu JSON
                            </button>
                        </div>
                        
                        <div class="export-format">
                            <h4>ncdu Format</h4>
                            <p>Compatible with ncdu tool for offline analysis</p>
                            <button class="btn-primary" onclick="exportScan('ncdu')">
                                📊 Export as ncdu JSON
                            </button>
                        </div>
                        
                        <div class="export-format">
                            <h4>SciDK Report</h4>
                            <p>Rich HTML report with analysis and suggestions</p>
                            <button class="btn-primary" onclick="exportScan('html')">
                                📄 Generate HTML Report
                            </button>
                        </div>
                        
                        <div class="export-format">
                            <h4>CSV Summary</h4>
                            <p>Tabular data for spreadsheet analysis</p>
                            <button class="btn-primary" onclick="exportScan('csv')">
                                📊 Export as CSV
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Import Modal -->
        <div id="import-modal" class="modal hidden">
            <div class="modal-content">
                <div class="modal-header">
                    <h2>📥 Import Existing Scan</h2>
                    <button onclick="closeImportModal()">×</button>
                </div>
                <div class="modal-body">
                    <div class="import-options">
                        <div class="import-method">
                            <h3>Upload Scan File</h3>
                            <div class="file-drop-zone" ondrop="handleFileDrop(event)" ondragover="allowDrop(event)">
                                <input type="file" id="scan-file-input" accept=".json" onchange="handleFileSelect(event)">
                                <p>Drop gdu or ncdu JSON file here, or click to select</p>
                                <p class="file-hint">Supported: *.json files from gdu --json or ncdu -o</p>
                            </div>
                        </div>
                        
                        <div class="import-method">
                            <h3>From URL</h3>
                            <input type="url" placeholder="https://example.com/scan_results.json" id="scan-url-input">
                            <button onclick="importFromURL()">Import from URL</button>
                        </div>
                        
                        <div class="import-method">
                            <h3>Paste JSON</h3>
                            <textarea placeholder="Paste gdu or ncdu JSON output here..." id="scan-json-input"></textarea>
                            <button onclick="importFromJSON()">Import JSON</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="/static/js/filesystem-scanner.js"></script>
</body>
</html>
```

---

## Backend Integration Architecture

## Backend Integration Architecture

### **Simplified ncdu-First Scanner**
```python
# scidk/core/filesystem_scanner.py
import subprocess
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional
import shutil
import uuid

class FilesystemScanner:
    """Simple, reliable filesystem scanning with ncdu"""
    
    def __init__(self):
        # Check for required tool
        if not shutil.which('ncdu'):
            raise RuntimeError(
                "ncdu not found. Please install: "
                "apt install ncdu (Ubuntu/Debian) or "
                "yum install ncdu (CentOS/RHEL) or "
                "brew install ncdu (macOS)"
            )
        
        # Optional: check for gdu for import compatibility
        self.gdu_available = shutil.which('gdu') is not None
    
    async def scan_directory(self, path: str, options: Dict = None) -> Dict:
        """Scan directory using ncdu - simple and reliable"""
        options = options or {}
        
        temp_file = f"/tmp/scidk_ncdu_{uuid.uuid4().hex}.json"
        
        try:
            # Build ncdu command
            cmd = ['ncdu', '-o', temp_file]
            
            # Add options (keep simple)
            if not options.get('cross_filesystems', False):
                cmd.append('-x')  # Don't cross filesystem boundaries
                
            cmd.append(str(path))
            
            # Run ncdu scan
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise RuntimeError(f"ncdu scan failed: {stderr.decode()}")
            
            # Read JSON output
            with open(temp_file, 'r') as f:
                scan_data = json.load(f)
            
            # Convert to standardized format
            standardized_data = self.convert_ncdu_to_standard(scan_data)
            
            # Enhance with SciDK intelligence
            enhanced_data = await self.enhance_scan_data(standardized_data, path)
            
            # Store in Neo4j
            await self.store_scan_results(enhanced_data, path)
            
            return enhanced_data
            
        except Exception as e:
            raise RuntimeError(f"Failed to scan directory: {e}")
        finally:
            # Cleanup
            Path(temp_file).unlink(missing_ok=True)
    
    def convert_ncdu_to_standard(self, ncdu_data: List) -> Dict:
        """Convert ncdu JSON format to standardized format"""
        
        def convert_item(item):
            """Recursively convert ncdu items to standard format"""
            if isinstance(item, list):
                # ncdu directory format: [size, name, [children...]]
                size, name = item[0], item[1]
                children = item[2:] if len(item) > 2 else []
                
                return {
                    "name": name,
                    "size": size,
                    "type": "directory",
                    "children": [convert_item(child) for child in children if isinstance(child, list)]
                }
            elif isinstance(item, dict):
                # ncdu file format: {"size": X, "name": "file.txt"}
                return {
                    "name": item.get("name", ""),
                    "size": item.get("size", 0),
                    "type": "file",
                    "children": []
                }
            
            return {"name": "unknown", "size": 0, "type": "file", "children": []}
        
        # ncdu format: [version, timestamp, root_item]
        if len(ncdu_data) >= 3:
            root_item = ncdu_data[2]
            return convert_item(root_item)
        
        return {"name": "empty", "size": 0, "type": "directory", "children": []}
    
    def import_existing_scan(self, file_content: str, format_type: str = 'auto') -> Dict:
        """Import existing ncdu or gdu scan file"""
        
        try:
            data = json.loads(file_content)
            
            # Auto-detect format (keep simple)
            if format_type == 'auto':
                if isinstance(data, list) and len(data) >= 3:
                    format_type = 'ncdu'
                elif isinstance(data, dict) and 'name' in data:
                    format_type = 'gdu'
                else:
                    raise ValueError("Cannot determine scan file format")
            
            # Convert to standard format if needed
            if format_type == 'ncdu':
                return self.convert_ncdu_to_standard(data)
            elif format_type == 'gdu':
                # gdu format is already similar to our standard format
                return data
            else:
                raise ValueError(f"Unsupported format: {format_type}")
                
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")
        except Exception as e:
            raise ValueError(f"Failed to import scan: {e}")
    
    async def enhance_scan_data(self, scan_data: Dict, base_path: str) -> Dict:
        """Add SciDK intelligence to scan results"""
        
        enhanced = scan_data.copy()
        enhanced['scidk_analysis'] = {
            'scan_timestamp': asyncio.get_event_loop().time(),
            'base_path': base_path,
            'tool_used': 'ncdu',
            'research_object_suggestions': await self.generate_ro_suggestions(scan_data),
            'file_type_analysis': self.analyze_file_types(scan_data),
            'duplicate_detection': await self.detect_duplicates(scan_data),
            'size_analysis': self.analyze_sizes(scan_data)
        }
        
        return enhanced
    
    async def generate_ro_suggestions(self, scan_data: Dict) -> List[Dict]:
        """Generate intelligent Research Object suggestions"""
        suggestions = []
        
        def analyze_directory(dir_data, path=""):
            """Simple directory analysis for RO suggestions"""
            if dir_data.get('type') != 'directory':
                return
                
            children = dir_data.get('children', [])
            if len(children) == 0:
                return
            
            # Count files and analyze patterns
            file_types = {}
            total_size = 0
            file_count = 0
            
            for child in children:
                if child.get('type') == 'file':
                    file_ext = Path(child.get('name', '')).suffix.lower()
                    file_types[file_ext] = file_types.get(file_ext, 0) + 1
                    total_size += child.get('size', 0)
                    file_count += 1
                elif child.get('type') == 'directory':
                    analyze_directory(child, f"{path}/{child.get('name', '')}")
            
            # Simple confidence calculation
            confidence = self.calculate_ro_confidence(file_types, file_count, total_size)
            
            if confidence > 0.6:  # 60% confidence threshold
                suggestions.append({
                    'path': path or dir_data.get('name', ''),
                    'name': f"{dir_data.get('name', 'Unknown')} Research Object",
                    'confidence': confidence,
                    'file_count': file_count,
                    'total_size': total_size,
                    'dominant_types': sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:3],
                    'suggestion_reasons': self.get_suggestion_reasons(file_types, file_count)
                })
        
        analyze_directory(scan_data)
        
        # Sort by confidence
        return sorted(suggestions, key=lambda x: x['confidence'], reverse=True)
    
    def calculate_ro_confidence(self, file_types: Dict, file_count: int, total_size: int) -> float:
        """Simple confidence calculation for RO suggestions"""
        confidence = 0.0
        
        # Basic criteria
        if file_count > 10:
            confidence += 0.3
        if total_size > 100 * 1024 * 1024:  # >100MB
            confidence += 0.2
        if len(file_types) <= 5 and file_count > 5:
            confidence += 0.3
            
        # Scientific file types
        scientific_extensions = {'.tiff', '.tif', '.fastq', '.fq', '.csv', '.tsv', '.h5', '.hdf5', '.nc'}
        scientific_files = sum(count for ext, count in file_types.items() if ext in scientific_extensions)
        if scientific_files / max(file_count, 1) > 0.5:
            confidence += 0.4
        
        return min(confidence, 1.0)
    
    def get_suggestion_reasons(self, file_types: Dict, file_count: int) -> List[str]:
        """Generate human-readable reasons for RO suggestion"""
        reasons = []
        
        if file_count > 50:
            reasons.append(f"Large collection ({file_count} files)")
            
        scientific_extensions = {
            '.tiff': 'microscopy images', 
            '.fastq': 'genomics data', 
            '.csv': 'analysis results', 
            '.py': 'analysis scripts',
            '.R': 'R analysis scripts'
        }
        
        for ext, description in scientific_extensions.items():
            if ext in file_types and file_types[ext] > 5:
                reasons.append(f"Contains {description}")
        
        return reasons
    
    def analyze_file_types(self, scan_data: Dict) -> Dict:
        """Simple file type analysis"""
        type_stats = {}
        
        def count_types(item):
            if item.get('type') == 'file':
                ext = Path(item.get('name', '')).suffix.lower()
                if ext not in type_stats:
                    type_stats[ext] = {'count': 0, 'size': 0}
                type_stats[ext]['count'] += 1
                type_stats[ext]['size'] += item.get('size', 0)
            
            for child in item.get('children', []):
                count_types(child)
        
        count_types(scan_data)
        return type_stats
    
    async def detect_duplicates(self, scan_data: Dict) -> List[Dict]:
        """Simple duplicate detection by size and name"""
        size_groups = {}
        
        def collect_files(item, path=""):
            current_path = f"{path}/{item.get('name', '')}" if path else item.get('name', '')
            
            if item.get('type') == 'file':
                size = item.get('size', 0)
                if size > 1024 * 1024:  # Only check files > 1MB
                    if size not in size_groups:
                        size_groups[size] = []
                    size_groups[size].append({
                        'path': current_path,
                        'name': item.get('name', ''),
                        'size': size
                    })
            
            for child in item.get('children', []):
                collect_files(child, current_path)
        
        collect_files(scan_data)
        
        # Find potential duplicates
        duplicates = []
        for size, files in size_groups.items():
            if len(files) > 1:
                duplicates.append({
                    'size': size,
                    'files': files,
                    'potential_savings': size * (len(files) - 1)
                })
        
        return sorted(duplicates, key=lambda x: x['potential_savings'], reverse=True)
    
    def analyze_sizes(self, scan_data: Dict) -> Dict:
        """Simple size analysis"""
        analysis = {
            'largest_directories': [],
            'total_size': 0
        }
        
        def collect_sizes(item, path=""):
            current_path = f"{path}/{item.get('name', '')}" if path else item.get('name', '')
            size = item.get('size', 0)
            
            if item.get('type') == 'directory' and size > 10 * 1024 * 1024:  # >10MB
                analysis['largest_directories'].append({
                    'path': current_path,
                    'name': item.get('name', ''),
                    'size': size,
                    'file_count': self.count_files(item)
                })
            
            analysis['total_size'] += size
            
            for child in item.get('children', []):
                collect_sizes(child, current_path)
        
        collect_sizes(scan_data)
        
        # Keep top 20 largest directories
        analysis['largest_directories'].sort(key=lambda x: x['size'], reverse=True)
        analysis['largest_directories'] = analysis['largest_directories'][:20]
        
        return analysis
    
    def count_files(self, item) -> int:
        """Count total files in directory tree"""
        count = 0
        if item.get('type') == 'file':
            count = 1
        
        for child in item.get('children', []):
            count += self.count_files(child)
        
        return count
    
    async def store_scan_results(self, scan_data: Dict, base_path: str):
        """Store scan results in Neo4j for querying"""
        # Implementation to store standardized scan data in Neo4j
        pass
    
    def export_scan(self, scan_data: Dict, format_type: str) -> str:
        """Export scan results in various formats"""
        
        if format_type == 'ncdu':
            # Convert back to ncdu format for compatibility
            ncdu_data = [1, int(asyncio.get_event_loop().time()), self.convert_to_ncdu_format(scan_data)]
            return json.dumps(ncdu_data, indent=2)
        
        elif format_type == 'gdu':
            # Export as gdu-compatible format
            return json.dumps(scan_data, indent=2)
        
        elif format_type == 'csv':
            return self.export_to_csv(scan_data)
        
        elif format_type == 'html':
            return self.generate_html_report(scan_data)
        
        else:
            raise ValueError(f"Unsupported export format: {format_type}")
    
    def convert_to_ncdu_format(self, data: Dict) -> List:
        """Convert standardized format back to ncdu format"""
        # Simple conversion for export compatibility
        def convert_item(item):
            if item.get('type') == 'directory':
                children = [convert_item(child) for child in item.get('children', [])]
                return [item.get('size', 0), item.get('name', ''), *children]
            else:
                return {"size": item.get('size', 0), "name": item.get('name', '')}
        
        return convert_item(data)
    
    def export_to_csv(self, scan_data: Dict) -> str:
        """Export scan data as CSV"""
        # Simple CSV export implementation
        lines = ["path,name,type,size"]
        
        def add_items(item, path=""):
            current_path = f"{path}/{item.get('name', '')}" if path else item.get('name', '')
            lines.append(f'"{current_path}","{item.get("name", "")}","{item.get("type", "")}",{item.get("size", 0)}')
            
            for child in item.get('children', []):
                add_items(child, current_path)
        
        add_items(scan_data)
        return "\n".join(lines)
    
    def generate_html_report(self, scan_data: Dict) -> str:
        """Generate simple HTML report"""
        return f"""
        <html>
        <head><title>SciDK Filesystem Scan Report</title></head>
        <body>
        <h1>Filesystem Scan Report</h1>
        <p>Total Size: {scan_data.get('size', 0)} bytes</p>
        <p>Scanned: {scan_data.get('name', 'Unknown')}</p>
        <p>Generated by SciDK using ncdu</p>
        </body>
        </html>
        """

### **Simplified Flask API Routes**
```python
# scidk/web/routes/filesystem_scanner.py
from flask import Blueprint, request, jsonify, send_file
from scidk.core.filesystem_scanner import FilesystemScanner
import asyncio
import io

scanner_bp = Blueprint('scanner', __name__, url_prefix='/api/scanner')
filesystem_scanner = FilesystemScanner()

@scanner_bp.route('/scan', methods=['POST'])
async def start_scan():
    """Start directory scan using ncdu"""
    data = request.json
    path = data.get('path')
    options = data.get('options', {})
    
    if not path:
        return jsonify({'error': 'Path is required'}), 400
    
    try:
        scan_results = await filesystem_scanner.scan_directory(path, options)
        return jsonify(scan_results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@scanner_bp.route('/import', methods=['POST'])
def import_scan():
    """Import existing ncdu or gdu scan file"""
    
    if 'file' in request.files:
        # File upload
        file = request.files['file']
        content = file.read().decode('utf-8')
    elif 'content' in request.json:
        # JSON content
        content = request.json['content']
    elif 'url' in request.json:
        # URL import (simple implementation)
        import requests
        response = requests.get(request.json['url'])
        content = response.text
    else:
        return jsonify({'error': 'No scan data provided'}), 400
    
    try:
        format_type = request.json.get('format', 'auto')
        scan_data = filesystem_scanner.import_existing_scan(content, format_type)
        
        # Enhance imported data
        enhanced_data = await filesystem_scanner.enhance_scan_data(
            scan_data, 
            scan_data.get('name', 'imported')
        )
        
        return jsonify(enhanced_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@scanner_bp.route('/export/<scan_id>/<format>')
def export_scan(scan_id, format):
    """Export scan results in various formats"""
    
    try:
        # Get scan data from storage
        scan_data = get_scan_data(scan_id)  # Simple implementation needed
        
        exported_data = filesystem_scanner.export_scan(scan_data, format)
        
        if format in ['gdu', 'ncdu']:
            return jsonify(json.loads(exported_data))
        elif format == 'csv':
            return send_file(
                io.StringIO(exported_data),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'scan_{scan_id}.csv'
            )
        elif format == 'html':
            return exported_data, 200, {'Content-Type': 'text/html'}
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@scanner_bp.route('/suggestions/<scan_id>')
def get_suggestions(scan_id):
    """Get Research Object suggestions for scan"""
    
    try:
        scan_data = get_scan_data(scan_id)
        suggestions = scan_data.get('scidk_analysis', {}).get('research_object_suggestions', [])
        return jsonify(suggestions)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@scanner_bp.route('/create-ro-from-suggestion', methods=['POST'])
def create_ro_from_suggestion():
    """Create Research Object from scanner suggestion"""
    
    data = request.json
    suggestion = data.get('suggestion')
    
    try:
        # Simple RO creation from suggested directory
        from scidk.core.research_objects import ResearchObjectManager
        ro_manager = ResearchObjectManager()
        
        ro_id, ro_crate = ro_manager.create_research_object_from_directory(
            suggestion['path'],
            suggestion['name'],
            session.get('user_id')
        )
        
        return jsonify({'ro_id': ro_id, 'ro_crate': ro_crate})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def get_scan_data(scan_id):
    """Simple helper to get scan data - implement based on storage choice"""
    # This could be from Neo4j, file cache, or database
    # Keep implementation simple for reliability
    pass
```

---

## Implementation Phases (Simplified for Reliability)

### **Phase 1: Core ncdu Integration (Week 1)**
- [ ] Verify ncdu installation and create simple Python wrapper
- [ ] Basic directory scanning with JSON output
- [ ] Simple web interface for starting scans
- [ ] Store scan results in temporary file storage

### **Phase 2: Basic UI (Week 2)**
- [ ] Simple directory tree visualization using existing libraries
- [ ] File type statistics (no complex charts)
- [ ] Basic export functionality (ncdu, CSV)
- [ ] Import existing ncdu scan files

### **Phase 3: Research Object Integration (Week 3)**
- [ ] Simple RO suggestion algorithm (file count + scientific extensions)
- [ ] One-click RO creation from suggestions
- [ ] Integration with existing RO-Crate browser
- [ ] Basic Neo4j storage for scan results

### **Phase 4: Polish & Testing (Week 4)**
- [ ] Error handling and edge cases
- [ ] Documentation and installation instructions
- [ ] Performance testing with real research datasets
- [ ] User feedback and iteration

**Total: 4 weeks to reliable filesystem scanner integration**

---

## Benefits of Simplified ncdu-First Approach

### **1. Reliability & Predictability**
- **Single Tool**: Only ncdu to install, configure, and debug
- **Consistent Behavior**: Same performance across all environments
- **Battle-Tested**: 15+ years of ncdu development and bug fixes
- **Simple Error Handling**: Predictable failure modes

### **2. Research-Appropriate Performance**
```
Real Research Workflow Timeline:
- Directory scan: 5 minutes (ncdu)
- RO creation: 30 minutes (user decisions)
- Metadata curation: 2+ hours (user work)
- Analysis: Days to weeks

5-minute scan time is negligible in research context
```

### **3. Easy Deployment & Support**
```bash
# Simple installation across platforms
apt install ncdu     # Ubuntu/Debian
yum install ncdu     # CentOS/RHEL  
brew install ncdu    # macOS
pacman -S ncdu       # Arch Linux
```

### **4. Import/Export Compatibility**
- **Import gdu scans**: When colleagues use gdu, import their results
- **Export ncdu format**: Share scans with other ncdu users
- **Standard JSON**: Process with any JSON-capable tool

### **5. Future-Proof Architecture**
- **Modular Design**: Easy to add gdu support later if needed
- **Standard Formats**: Not locked into proprietary formats
- **Tool Independence**: Could switch to other scanners if needed

---

## Optional: gdu Support as Enhancement

If performance becomes critical later, add gdu as an option:

```python
# Simple preference-based tool selection
SCANNER_TOOL = os.environ.get('SCIDK_SCANNER', 'ncdu')

class FilesystemScanner:
    def __init__(self):
        if SCANNER_TOOL == 'gdu' and shutil.which('gdu'):
            self.scanner = 'gdu'
        elif shutil.which('ncdu'):
            self.scanner = 'ncdu'
        else:
            raise RuntimeError("ncdu not found. Please install ncdu.")
    
    async def scan_directory(self, path, options=None):
        if self.scanner == 'gdu':
            return await self.scan_with_gdu(path, options)
        else:
            return await self.scan_with_ncdu(path, options)
```

**Users who need speed** can set `SCIDK_SCANNER=gdu`  
**Everyone else** gets reliable ncdu by default

---

## Integration with RO-Crate Workflow (Simplified)

### **Direct ncdu → Research Object Pipeline**
```python
# Simple, reliable workflow from scan to RO-Crate
class ScanToROPipeline:
    def __init__(self):
        self.scanner = FilesystemScanner()  # ncdu-based
        self.ro_manager = ResearchObjectManager()
    
    async def scan_and_suggest_ros(self, path: str):
        """Scan directory and suggest Research Objects"""
        
        # 1. Simple scan with ncdu
        scan_results = await self.scanner.scan_directory(path)
        
        # 2. Generate suggestions (keep algorithm simple)
        suggestions = scan_results['scidk_analysis']['research_object_suggestions']
        
        # 3. Present to user for selection
        return suggestions
    
    async def create_ro_from_scan_suggestion(self, suggestion: Dict, user_id: str):
        """Create RO-Crate from scanner suggestion"""
        
        # Simple RO-Crate creation with suggested files
        ro_id, ro_crate = self.ro_manager.create_research_object(
            name=suggestion['name'],
            author_id=user_id,
            description=f"Research object created from directory: {suggestion['path']}"
        )
        
        # Add files from scan suggestion (keep simple)
        for file_path in suggestion.get('files', []):
            await self.ro_manager.add_file_to_ro(ro_id, file_path)
        
        return ro_id, ro_crate
```

### **User Experience: Simple One-Click RO Creation**
```javascript
// Simple user workflow
async function createROFromSuggestion(suggestionId) {
    const suggestion = suggestions.find(s => s.id === suggestionId);
    
    const response = await fetch('/api/scanner/create-ro-from-suggestion', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({suggestion})
    });
    
    const result = await response.json();
    
    if (response.ok) {
        // Switch to RO-Crate browser with new RO selected
        window.location.href = `/ro-crates/${result.ro_id}`;
    }
}
```

---

## Benefits of ncdu-First Integration

### **1. Reliability & Consistency**
- **Single Tool**: Only ncdu to install, configure, and support
- **Predictable Performance**: 5-10 minutes for large datasets consistently
- **Cross-Platform**: Works identically on Linux, macOS, Windows
- **Battle-Tested**: 15+ years of development, handles edge cases

### **2. Research-Appropriate Performance**
```
Real Research Workflow Timeline:
┌─────────────────────────────────────────────────────────────┐
│ Directory scan (ncdu):     5 minutes                       │
│ Review suggestions:        10 minutes                      │  
│ RO creation decisions:     30 minutes                      │
│ Metadata curation:         2+ hours                       │
│ Analysis & interpretation: Days to weeks                   │
└─────────────────────────────────────────────────────────────┘

5-minute scan time is negligible in research context
Performance optimization not worth reliability trade-offs
```

### **3. Easy Deployment & Support**
```bash
# Simple, universal installation
sudo apt install ncdu     # Ubuntu/Debian
sudo yum install ncdu     # CentOS/RHEL  
brew install ncdu         # macOS
pacman -S ncdu           # Arch Linux

# Works on all research computing environments:
# - HPC login nodes
# - Lab workstations  
# - Cloud instances
# - Local laptops
```

### **4. Standards-Based Workflow**
- **JSON Output**: Standard format for data exchange
- **Tool Interoperability**: Import/export ncdu scans across systems
- **Future-Proof**: Not locked into proprietary formats
- **Community**: Large user base for troubleshooting

### **5. Import/Export Compatibility**
```python
# Support for both ncdu and gdu scans
def import_any_scan(file_content):
    """Import ncdu or gdu scan files"""
    
    # Auto-detect format
    data = json.loads(file_content)
    
    if isinstance(data, list):
        # ncdu format: [version, timestamp, tree]
        return convert_ncdu_scan(data)
    elif isinstance(data, dict):
        # gdu format: {name, size, children}
        return data  # Already compatible
```

**Colleagues using gdu?** Import their scan results  
**Sharing with ncdu users?** Export in native format  
**Need CSV for analysis?** Simple export option

### **6. Simplified Architecture Benefits**
- **Fewer Dependencies**: Only ncdu required
- **Simpler Testing**: One tool, one code path
- **Easier Debugging**: Predictable behavior
- **Lower Maintenance**: Less code to maintain
- **Faster Development**: Focus on features, not tool integration

This approach transforms filesystem scanning from a complex, tool-dependent process into a **simple, reliable system** that automatically discovers research datasets and suggests optimal organization strategies. By prioritizing **reliability over performance optimization**, SciDK provides researchers with a tool that works consistently across all computing environments - from local laptops to HPC clusters to cloud instances.

**Core Philosophy**: Better to have a tool that reliably scans directories in 5 minutes than one that sometimes scans in 30 seconds but fails on 20% of systems.