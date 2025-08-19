# SciDK GDU-Powered Filesystem Scanner: Standards-Based Directory Analysis

## Vision: Leverage Best-in-Class Filesystem Tools

Instead of building custom directory scanning, SciDK integrates **gdu** and **ncdu** - proven, fast, and accurate filesystem analysis tools. This follows our core principle: **use existing tools, enhance with intelligence**.

```
┌─────────────────────────────────────────────────────────────┐
│                    Filesystem Analysis                      │
│                                                             │
│  gdu/ncdu Tools ────────► JSON Output ────────► Neo4j      │
│  (Proven Performance)     (Standard Format)    (Intelligence)│
│                                                             │
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

## Why gdu/ncdu Over Custom Scanning

### **Performance & Reliability**
- **gdu**: Up to 10x faster than `du`, optimized for large datasets
- **ncdu**: Battle-tested, handles edge cases (symlinks, permissions, etc.)
- **Cross-platform**: Works on Linux, macOS, Windows
- **Memory efficient**: Can scan terabyte directories without issues

### **JSON Output Integration**
```bash
# gdu provides structured JSON output perfect for processing
gdu --json --no-progress /data/research > scan_results.json

# ncdu can export to JSON format  
ncdu -o scan_results.json /data/research
```

### **Standards Compliance**
- Proven tools with years of development
- Consistent output format across environments
- No need to reinvent filesystem traversal logic
- Focus SciDK development on value-add features

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

### **GDU/NCDU Tool Integration**
```python
# scidk/core/filesystem_scanner.py
import subprocess
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Union
import shutil

class FilesystemScanner:
    """Integrate gdu and ncdu for filesystem analysis"""
    
    def __init__(self):
        self.preferred_tool = self.detect_available_tools()
        self.scan_cache = {}
    
    def detect_available_tools(self) -> str:
        """Detect which tools are available on the system"""
        if shutil.which('gdu'):
            return 'gdu'
        elif shutil.which('ncdu'):
            return 'ncdu'
        else:
            raise RuntimeError("Neither gdu nor ncdu found. Please install one of them.")
    
    async def scan_directory(self, path: str, options: Dict = None) -> Dict:
        """Scan directory using gdu or ncdu"""
        options = options or {}
        
        if self.preferred_tool == 'gdu':
            return await self.scan_with_gdu(path, options)
        else:
            return await self.scan_with_ncdu(path, options)
    
    async def scan_with_gdu(self, path: str, options: Dict) -> Dict:
        """Use gdu for fast directory scanning"""
        
        cmd = ['gdu', '--json', '--no-progress']
        
        # Add options
        if not options.get('include_hidden', True):
            cmd.append('--no-hidden')
        if not options.get('follow_symlinks', False):
            cmd.append('--no-follow-symlinks')
        if not options.get('cross_filesystems', False):
            cmd.append('--no-cross')
            
        cmd.append(str(path))
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise RuntimeError(f"gdu failed: {stderr.decode()}")
            
            scan_data = json.loads(stdout.decode())
            
            # Enhance with SciDK intelligence
            enhanced_data = await self.enhance_scan_data(scan_data, path)
            
            # Store in Neo4j
            await self.store_scan_results(enhanced_data, path)
            
            return enhanced_data
            
        except Exception as e:
            raise RuntimeError(f"Failed to scan with gdu: {e}")
    
    async def scan_with_ncdu(self, path: str, options: Dict) -> Dict:
        """Use ncdu for directory scanning with JSON export"""
        
        temp_file = f"/tmp/scidk_ncdu_{hash(path)}.json"
        
        cmd = ['ncdu', '-o', temp_file]
        
        if not options.get('follow_symlinks', False):
            cmd.append('-x')  # Don't cross filesystem boundaries
            
        cmd.append(str(path))
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            await process.communicate()
            
            if process.returncode != 0:
                raise RuntimeError("ncdu scanning failed")
            
            # Read the JSON output
            with open(temp_file, 'r') as f:
                scan_data = json.load(f)
            
            # Convert ncdu format to standardized format
            standardized_data = self.convert_ncdu_to_standard(scan_data)
            
            # Enhance with SciDK intelligence
            enhanced_data = await self.enhance_scan_data(standardized_data, path)
            
            # Store in Neo4j
            await self.store_scan_results(enhanced_data, path)
            
            # Cleanup
            Path(temp_file).unlink(missing_ok=True)
            
            return enhanced_data
            
        except Exception as e:
            raise RuntimeError(f"Failed to scan with ncdu: {e}")
    
    def convert_ncdu_to_standard(self, ncdu_data: List) -> Dict:
        """Convert ncdu JSON format to standardized gdu-like format"""
        
        def convert_item(item):
            if isinstance(item, dict):
                return {
                    "name": item.get("name", ""),
                    "size": item.get("dsize", 0),
                    "type": "directory" if item.get("type") == "dir" else "file",
                    "children": [convert_item(child) for child in item.get("children", [])]
                }
            return item
        
        # ncdu format: [version, timestamp, root_item]
        if len(ncdu_data) >= 3:
            root_item = ncdu_data[2]
            return convert_item(root_item)
        
        return {}
    
    async def enhance_scan_data(self, scan_data: Dict, base_path: str) -> Dict:
        """Add SciDK intelligence to scan results"""
        
        enhanced = scan_data.copy()
        enhanced['scidk_analysis'] = {
            'scan_timestamp': asyncio.get_event_loop().time(),
            'base_path': base_path,
            'research_object_suggestions': await self.generate_ro_suggestions(scan_data),
            'file_type_analysis': self.analyze_file_types(scan_data),
            'duplicate_detection': await self.detect_duplicates(scan_data),
            'size_analysis': self.analyze_sizes(scan_data)
        }
        
        return enhanced
    
    async def generate_ro_suggestions(self, scan_data: Dict) -> List[Dict]:
        """Generate intelligent Research Object suggestions"""
        suggestions = []
        
        # Look for coherent directory structures
        def analyze_directory(dir_data, path=""):
            if dir_data.get('type') != 'directory':
                return
                
            children = dir_data.get('children', [])
            if len(children) == 0:
                return
            
            # Analyze file patterns
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
            
            # Suggest RO if directory has coherent structure
            confidence = self.calculate_ro_confidence(file_types, file_count, total_size)
            
            if confidence > 0.5:  # 50% confidence threshold
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
        """Calculate confidence that directory should be a Research Object"""
        confidence = 0.0
        
        # High file count suggests organized research
        if file_count > 10:
            confidence += 0.3
        
        # Large size suggests important data
        if total_size > 1024 * 1024 * 100:  # 100MB
            confidence += 0.2
        
        # Coherent file types suggest purpose
        if len(file_types) <= 5 and file_count > 5:  # Few types, many files
            confidence += 0.3
        
        # Scientific file extensions
        scientific_extensions = {'.tiff', '.tif', '.fastq', '.fq', '.csv', '.tsv', '.h5', '.hdf5', '.nc', '.cdf'}
        scientific_files = sum(count for ext, count in file_types.items() if ext in scientific_extensions)
        if scientific_files / max(file_count, 1) > 0.5:
            confidence += 0.4
        
        return min(confidence, 1.0)
    
    def get_suggestion_reasons(self, file_types: Dict, file_count: int) -> List[str]:
        """Generate human-readable reasons for RO suggestion"""
        reasons = []
        
        if file_count > 50:
            reasons.append(f"Large collection ({file_count} files)")
        
        scientific_extensions = {'.tiff': 'microscopy images', '.fastq': 'genomics data', 
                               '.csv': 'analysis results', '.py': 'analysis scripts'}
        
        for ext, description in scientific_extensions.items():
            if ext in file_types and file_types[ext] > 5:
                reasons.append(f"Contains {description}")
        
        return reasons
    
    def analyze_file_types(self, scan_data: Dict) -> Dict:
        """Analyze file type distribution"""
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
        """Detect potential duplicate files based on size and name patterns"""
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
        
        # Find potential duplicates (same size)
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
        """Analyze size distribution and identify large directories"""
        analysis = {
            'largest_directories': [],
            'size_distribution': {},
            'total_size': 0
        }
        
        def collect_sizes(item, path=""):
            current_path = f"{path}/{item.get('name', '')}" if path else item.get('name', '')
            size = item.get('size', 0)
            
            if item.get('type') == 'directory' and size > 1024 * 1024 * 10:  # > 10MB
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
        
        # Sort largest directories
        analysis['largest_directories'].sort(key=lambda x: x['size'], reverse=True)
        analysis['largest_directories'] = analysis['largest_directories'][:20]  # Top 20
        
        return analysis
    
    def count_files(self, item) -> int:
        """Count total files in a directory tree"""
        count = 0
        if item.get('type') == 'file':
            count = 1
        
        for child in item.get('children', []):
            count += self.count_files(child)
        
        return count
    
    async def store_scan_results(self, scan_data: Dict, base_path: str):
        """Store scan results in Neo4j for querying"""
        # Implementation to store in Neo4j knowledge graph
        pass
    
    def import_existing_scan(self, file_content: str, format_type: str = 'auto') -> Dict:
        """Import existing gdu or ncdu scan file"""
        
        try:
            data = json.loads(file_content)
            
            # Auto-detect format
            if format_type == 'auto':
                if isinstance(data, list) and len(data) >= 3:
                    format_type = 'ncdu'
                elif isinstance(data, dict) and 'name' in data:
                    format_type = 'gdu'
                else:
                    raise ValueError("Cannot determine scan file format")
            
            # Convert to standard format if needed
            if format_type == 'ncdu':
                data = self.convert_ncdu_to_standard(data)
            
            return data
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format: {e}")
        except Exception as e:
            raise ValueError(f"Failed to import scan: {e}")

    def export_scan(self, scan_data: Dict, format_type: str) -> Union[str, bytes]:
        """Export scan results in various formats"""
        
        if format_type == 'gdu':
            return json.dumps(scan_data, indent=2)
        
        elif format_type == 'ncdu':
            # Convert to ncdu format
            ncdu_data = [1, int(asyncio.get_event_loop().time()), self.convert_to_ncdu_format(scan_data)]
            return json.dumps(ncdu_data, indent=2)
        
        elif format_type == 'csv':
            return self.export_to_csv(scan_data)
        
        elif format_type == 'html':
            return self.generate_html_report(scan_data)
        
        else:
            raise ValueError(f"Unsupported export format: {format_type}")
```

### **Flask API Routes**
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
    """Start directory scan using gdu/ncdu"""
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
    """Import existing gdu or ncdu scan file"""
    
    if 'file' in request.files:
        # File upload
        file = request.files['file']
        content = file.read().decode('utf-8')
    elif 'content' in request.json:
        # JSON content
        content = request.json['content']
    elif 'url' in request.json:
        # URL import
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
        # Get scan data from storage (Neo4j or cache)
        scan_data = get_scan_data(scan_id)  # Implementation needed
        
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
        # Create RO-Crate from suggested directory
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
```

---

## Implementation Phases

### **Phase 1: Core Tool Integration (Week 1-2)**
- [ ] Detect and integrate gdu/ncdu tools
- [ ] Basic directory scanning with JSON output
- [ ] Simple web interface for starting scans
- [ ] Store scan results in temporary storage

### **Phase 2: Enhanced UI (Week 3-4)**
- [ ] Rich directory tree visualization
- [ ] File type analysis and statistics
- [ ] Size distribution charts
- [ ] Basic export functionality

### **Phase 3: Intelligence Layer (Week 5-6)**
- [ ] Research Object suggestions algorithm
- [ ] Duplicate detection and analysis
- [ ] Integration with Neo4j for scan storage
- [ ] Smart suggestions based on file patterns

### **Phase 4: Import/Export Features (Week 7-8)**
- [ ] Import existing gdu/ncdu scan files
- [ ] Multiple export formats (JSON, CSV, HTML)
- [ ] Scan comparison and history
- [ ] Integration with RO-Crate creation workflow

### **Phase 5: Advanced Features (Week 9-10)**
- [ ] Real-time scan progress updates
- [ ] Scheduled/automated scanning
- [ ] Scan sharing and collaboration
- [ ] Integration with cloud storage (rclone)

---

## Integration with RO-Crate Workflow

### **Seamless Directory → Research Object Pipeline**
```python
# Complete workflow from scan to RO-Crate
class ScanToROPipeline:
    def __init__(self):
        self.scanner = FilesystemScanner()
        self.ro_manager = ResearchObjectManager()
    
    async def scan_and_suggest_ros(self, path: str):
        """Scan directory and suggest Research Objects"""
        
        # 1. Scan with gdu/ncdu
        scan_results = await self.scanner.scan_directory(path)
        
        # 2. Generate intelligent suggestions
        suggestions = scan_results['scidk_analysis']['research_object_suggestions']
        
        # 3. Present to user for selection
        return suggestions
    
    async def create_ro_from_scan_suggestion(self, suggestion: Dict, user_id: str):
        """Create RO-Crate from scanner suggestion"""
        
        # Create RO-Crate with suggested files
        ro_id, ro_crate = self.ro_manager.create_research_object(
            name=suggestion['name'],
            author_id=user_id,
            description=f"Research object created from directory scan of {suggestion['path']}"
        )
        
        # Add files from scan suggestion
        for file_path in suggestion.get('files', []):
            await self.ro_manager.add_file_to_ro(ro_id, file_path)
        
        return ro_id, ro_crate
```

### **User Experience: One-Click RO Creation**
```javascript
// User clicks "Create Research Object" from scan suggestion
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

## Benefits of gdu/ncdu Integration

### **1. Performance & Reliability**
- **Proven Tools**: gdu is optimized for speed, ncdu handles edge cases
- **No Reinvention**: Leverage years of filesystem tool development
- **Cross-Platform**: Works on all major operating systems

### **2. Standards-Based Workflow**
- **JSON Output**: Standard format for data exchange
- **Tool Interoperability**: Users can use scan results with other tools
- **Import/Export**: Share scans across different SciDK instances

### **3. Enhanced Intelligence**
- **Research Object Discovery**: AI-powered suggestions for dataset organization
- **Duplicate Detection**: Identify wasted storage space
- **Pattern Recognition**: Detect scientific data patterns automatically

### **4. Seamless Integration**
- **RO-Crate Creation**: Direct pipeline from scan to research object
- **Neo4j Storage**: Scan results feed into knowledge graph
- **File Browser Integration**: Scan results enhance file discovery

This approach transforms filesystem scanning from a manual, custom process into an intelligent, standards-based system that automatically discovers research datasets and suggests optimal organization strategies.