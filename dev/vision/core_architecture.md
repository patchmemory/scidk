# SciDK Core Architecture: Platform, Interpreters, and Plugins

## Architecture Overview

SciDK uses a three-tier extension model:
1. **Core Platform** - Essential infrastructure
2. **File Interpreters** - Components that understand specific data "languages"
3. **Plugins** - Full-featured capability extensions

```
┌─────────────────────────────────────────────────────────────┐
│                      Core Platform                          │
│  • Authentication  • Knowledge Graph  • FilesystemManager   │
│  • Chat Interface  • Interpreter Registry • Plugin Manager  │
└─────────────────────────────────────────────────────────────┘
           ↓                                      ↓
┌─────────────────────┐              ┌──────────────────────┐
│  File Interpreters  │              │      Plugins         │
│  (Understand Data)  │              │  (Major Features)    │
├─────────────────────┤              ├──────────────────────┤
│ • DICOM Interpreter │              │ • PubMed Search      │
│ • FASTQ Interpreter │              │ • LIMS Integration   │
│ • Python Interpreter│              │ • Facility Scheduler │
│ • CSV Interpreter   │              │ • Archive Transfer   │
└─────────────────────┘              └──────────────────────┘
```

### The Polyglot Platform

SciDK is a **polyglot data platform** - it speaks many data languages through specialized interpreters. Each interpreter understands a specific "language" of scientific data:

- **DICOM Interpreter** speaks medical imaging
- **FASTQ Interpreter** speaks genomic sequencing  
- **Python Interpreter** speaks code and computational methods
- **MaxQuant Interpreter** speaks mass spectrometry

---

## 1. Core Platform Components

### 1.1 FilesystemManager (Built-in)

```python
class FilesystemManager:
    """Core component that discovers and tracks all files"""
    
    def __init__(self):
        self.interpreter_registry = InterpreterRegistry()
        self.pattern_matcher = PatternMatcher()
        self.scan_locations = []
        self.file_graph = KnowledgeGraph()
    
    def scan_directory(self, path: Path, recursive=True):
        """Core scanning - creates basic Dataset nodes"""
        for file_path in path.rglob('*'):
            # Create basic node with universal metadata
            dataset = self.create_dataset_node(file_path)
            
            # Trigger interpretation pipeline
            self.interpret_dataset(dataset)
    
    def create_dataset_node(self, file_path: Path):
        """Creates basic graph node for ANY file"""
        return {
            'id': generate_uuid(),
            'path': str(file_path),
            'filename': file_path.name,
            'extension': file_path.suffix,
            'size_bytes': file_path.stat().st_size,
            'created': file_path.stat().st_ctime,
            'modified': file_path.stat().st_mtime,
            'mime_type': detect_mime_type(file_path),
            'checksum': calculate_checksum(file_path),
            'lifecycle_state': 'active'
        }
    
    def interpret_dataset(self, dataset):
        """Triggers appropriate interpreters based on patterns and file type"""
        # First check pattern-based rules
        interpreters = self.pattern_matcher.match_interpreters(dataset)
        
        # Fall back to extension-based matching
        if not interpreters:
            interpreters = self.interpreter_registry.get_interpreters(dataset['extension'])
        
        for interpreter in interpreters:
            interpreter.process_async(dataset)
```

### 1.2 Knowledge Graph (Built-in)

```python
class CoreKnowledgeGraph:
    """Base graph that all components write to"""
    
    base_schema = {
        'nodes': {
            'Dataset': {
                'properties': ['path', 'size_bytes', 'checksum', 'lifecycle_state'],
                'required': True  # Every file becomes a Dataset
            },
            'User': {
                'properties': ['username', 'email', 'groups'],
                'required': True
            }
        },
        'relationships': {
            'CREATED_BY': {'from': 'Dataset', 'to': 'User'},
            'DERIVED_FROM': {'from': 'Dataset', 'to': 'Dataset'},
            'STORED_IN': {'from': 'Dataset', 'to': 'StorageLocation'}
        }
    }
```

### 1.3 Chat Interface (Built-in)

```python
class ChatInterface:
    """Unified conversational interface"""
    
    def process_query(self, query: str):
        # Core understands basic file queries
        if self.is_file_query(query):
            return self.handle_file_query(query)
        
        # Delegate to plugins for domain-specific queries
        return self.delegate_to_plugins(query)
```

---

## 2. File Interpreters (Data Language Understanding)

### What Are Interpreters?

**Interpreters are NOT plugins.** They are components that understand specific data "languages":
- Each interpreter speaks one or more data formats
- They interpret file contents into structured meaning
- Run in multiple environments (Python, Bash, Perl, R)
- Can be user-defined with pattern-based rules
- Results are cached in the knowledge graph with versioning

### Interpreter Management

```python
class InterpreterRegistry:
    """Manages available interpreters and their assignment rules"""
    
    def __init__(self):
        self.interpreters = {}  # id -> InterpreterDefinition
        self.rules = []  # Pattern-based rules for interpreter selection
        self.file_type_assignments = {}  # extension -> interpreter_id
        
    def register_interpreter(self, interpreter_def):
        """Register a new interpreter"""
        self.interpreters[interpreter_def.id] = interpreter_def
        
    def get_interpreter_for_file(self, file_path: Path):
        """Determine which interpreter to use based on rules and patterns"""
        # Check pattern rules first (highest priority)
        for rule in sorted(self.rules, key=lambda r: r.priority, reverse=True):
            if rule.matches(file_path):
                return self.interpreters[rule.interpreter_id]
        
        # Fall back to extension-based assignment
        ext = file_path.suffix
        if ext in self.file_type_assignments:
            return self.interpreters[self.file_type_assignments[ext]]
        
        return None
```

### Interpreter Interface

```python
class FileInterpreter(ABC):
    """Base class for all file interpreters"""
    
    def __init__(self, definition: InterpreterDefinition):
        self.id = definition.id
        self.name = definition.name
        self.runtime = definition.runtime  # python | bash | perl | r
        self.languages = definition.capabilities['extensions']
        self.patterns = definition.capabilities.get('file_patterns', [])
        self.script = definition.script
        
    @abstractmethod
    def interpret(self, file_path: Path) -> InterpretationResult:
        """Interpret file contents into structured meaning"""
        pass
    
    def process(self, dataset_node: Dict) -> Dict:
        """Add interpreted meaning to dataset node"""
        try:
            result = self.interpret(Path(dataset_node['path']))
            
            # Cache interpretation in knowledge graph
            self.cache_interpretation(dataset_node, result)
            
            # Add to dataset node
            dataset_node['interpretation'][self.id] = {
                'data': result.data,
                'status': result.status,
                'interpreter_version': self.version,
                'timestamp': datetime.now()
            }
            
            if result.errors:
                dataset_node['interpretation_errors'] = result.errors
                
            return dataset_node
            
        except Exception as e:
            # Record interpretation failure
            dataset_node['interpretation_errors'] = [{
                'interpreter': self.id,
                'error_type': 'INTERPRETATION_FAILED',
                'details': str(e),
                'timestamp': datetime.now()
            }]
            return dataset_node
```

### Example Interpreters

#### Python Interpreter for DICOM (Built-in)
```python
class DICOMInterpreter(FileInterpreter):
    """Interprets medical imaging metadata"""
    
    runtime = "python"
    languages = ['.dcm', '.dicom']
    
    def interpret(self, file_path: Path):
        import pydicom
        ds = pydicom.dcmread(file_path, stop_before_pixels=True)
        
        return InterpretationResult(
            status='success',
            data={
                'patient_id': getattr(ds, 'PatientID', None),
                'study_date': getattr(ds, 'StudyDate', None),
                'modality': getattr(ds, 'Modality', None),
                'body_part': getattr(ds, 'BodyPartExamined', None),
                'image_dimensions': (ds.Rows, ds.Columns) if hasattr(ds, 'Rows') else None
            }
        )
```

#### Bash Interpreter for TIFF Metadata (User-defined)
```bash
#!/bin/bash
# User-defined interpreter in Bash for TIFF files

FILE_PATH="$1"
OUTPUT_FILE="$2"

# Use exiftool to extract metadata
if command -v exiftool &> /dev/null; then
    exiftool -json "$FILE_PATH" | jq '{
        width: .[0].ImageWidth,
        height: .[0].ImageHeight,
        bit_depth: .[0].BitsPerSample,
        software: .[0].Software,
        channels: .[0].SamplesPerPixel,
        x_resolution: .[0].XResolution,
        y_resolution: .[0].YResolution
    }' > "$OUTPUT_FILE"
else
    echo '{"error": "exiftool not installed"}' > "$OUTPUT_FILE"
fi
```

#### Pattern-Based Rule Example
```python
class InterpreterRule:
    """Rule for selecting interpreters based on file patterns"""
    
    def __init__(self):
        self.name = "Microscopy TIFF with OME metadata"
        self.priority = 10
        self.conditions = {
            "path_pattern": r".*/microscopy/.*\.tiff?$",
            "sibling_file": "metadata.xml",  # OME-TIFF indicator
            "min_size_mb": 100
        }
        self.interpreter_id = "ome_tiff_interpreter"
        self.config = {
            "extract_channels": True,
            "parse_ome_xml": True
        }
    
    def matches(self, file_path: Path) -> bool:
        """Check if file matches this rule"""
        # Check path pattern
        if not re.match(self.conditions['path_pattern'], str(file_path)):
            return False
            
        # Check for sibling file
        sibling = file_path.parent / self.conditions['sibling_file']
        if not sibling.exists():
            return False
            
        # Check file size
        size_mb = file_path.stat().st_size / (1024 * 1024)
        if size_mb < self.conditions['min_size_mb']:
            return False
            
        return True
```

#### Python Code Interpreter (Understands dependencies)
```python
class PythonCodeInterpreter(FileInterpreter):
    """Interprets Python code structure and dependencies"""
    
    runtime = "python"
    languages = ['.py', '.pyw', '.ipynb']
    
    def interpret(self, file_path: Path):
        import ast
        
        with open(file_path, 'r') as f:
            try:
                tree = ast.parse(f.read())
                
                return InterpretationResult(
                    status='success',
                    data={
                        'imports': self.extract_imports(tree),
                        'functions': [n.name for n in ast.walk(tree) 
                                    if isinstance(n, ast.FunctionDef)],
                        'classes': [n.name for n in ast.walk(tree) 
                                  if isinstance(n, ast.ClassDef)],
                        'dependencies': self.identify_packages(tree),
                        'docstring': ast.get_docstring(tree) or ""
                    }
                )
            except SyntaxError as e:
                return InterpretationResult(
                    status='error',
                    errors=[{
                        'type': 'SYNTAX_ERROR',
                        'line': e.lineno,
                        'details': str(e)
                    }]
                )
```

### Interpreter Configuration & Management

#### Settings UI
Users configure interpreters through a settings interface that allows:
- **File type assignments**: Choose which interpreter handles each extension
- **Pattern rules**: Define REGEX patterns for specific file structures
- **Priority ordering**: Set precedence when multiple interpreters match
- **Runtime selection**: Choose execution environment (Python, Bash, Perl, R)
- **Custom interpreters**: Create and test new interpreters

#### Registration Configuration
```yaml
# interpreters.yaml - Language registry
interpreters:
  - id: dicom_medical
    name: "DICOM Medical Imaging"
    runtime: python
    languages: [.dcm, .dicom]
    description: "Interprets medical imaging metadata"
    
  - id: tiff_microscopy
    name: "TIFF Microscopy"
    runtime: bash
    languages: [.tif, .tiff]
    patterns:
      - "IMG_\\d{4}_.*\\.tiff?"  # Numbered microscopy images
    dependencies: [exiftool, jq]
    
  - id: genomics_fastq
    name: "FASTQ Sequencing"
    runtime: python
    languages: [.fastq, .fq, .fastq.gz]
    patterns:
      - ".*_R[12]_\\d{3}\\.fastq\\.gz$"  # Illumina paired-end
    
  - id: python_code
    name: "Python Code Analyzer"
    runtime: python
    languages: [.py, .ipynb]
    features:
      - dependency_extraction
      - function_mapping
      - import_analysis
    
  - id: proteomics_maxquant
    name: "MaxQuant Proteomics"
    runtime: python
    specific_files: [proteinGroups.txt, peptides.txt]
    description: "Interprets MaxQuant mass spec output"

# Pattern rules for special cases
pattern_rules:
  - name: "OME-TIFF Microscopy"
    priority: 10
    conditions:
      path: ".*/microscopy/.*\\.tiff?$"
      sibling_file: "metadata.xml"
    use_interpreter: ome_tiff_advanced
    
  - name: "Analysis CSVs"
    priority: 5
    conditions:
      path: ".*/analysis/.*\\.csv$"
    use_interpreter: scientific_csv_interpreter
```

---

## 3. Plugins (Major Feature Extensions)

### What Are Plugins?

**Plugins are full-featured extensions** that:
- Add new capabilities to SciDK
- Can have their own UI components
- Can expose API endpoints
- Can run background tasks
- Can query and modify the knowledge graph
- Require configuration and setup

### Plugin Interface

```python
class SciDKPlugin(ABC):
    """Base class for full plugins"""
    
    @abstractmethod
    def get_capabilities(self) -> PluginCapabilities:
        """Declare what this plugin provides"""
        pass
    
    @abstractmethod
    def register_routes(self, app):
        """Add API endpoints"""
        pass
    
    @abstractmethod
    def register_ui_components(self) -> Dict:
        """Add UI elements"""
        pass
    
    @abstractmethod
    def handle_query(self, query: str) -> Optional[Response]:
        """Handle natural language queries"""
        pass
```

### Example Plugins

#### PubMed Plugin (Full feature)
```python
class PubMedPlugin(SciDKPlugin):
    """Integrate literature search"""
    
    def get_capabilities(self):
        return {
            'search': True,
            'import': True,
            'citation_tracking': True,
            'full_text_analysis': True
        }
    
    def register_routes(self, app):
        app.route('/plugins/pubmed/search', self.search_papers)
        app.route('/plugins/pubmed/import', self.import_citations)
    
    def handle_query(self, query):
        if 'paper' in query or 'publication' in query:
            return self.search_papers(query)
```

#### LIMS Integration Plugin
```python
class LIMSPlugin(SciDKPlugin):
    """Connect to laboratory information management system"""
    
    def get_capabilities(self):
        return {
            'sample_tracking': True,
            'result_import': True,
            'workflow_automation': True
        }
    
    # Full implementation with API connections, etc.
```

---

## 4. How They Work Together

### Scenario: User adds a directory with mixed data

```python
# 1. Core FilesystemManager scans directory
/research/project_2024/
  ├── sequences/
  │   ├── sample1_R1_001.fastq.gz  # Matches Illumina pattern
  │   └── sample2_R2_001.fastq.gz
  ├── microscopy/
  │   ├── IMG_0001_channel1.tiff   # Matches microscopy pattern
  │   ├── IMG_0002_channel2.tiff
  │   └── metadata.xml              # OME-TIFF indicator
  ├── analysis/
  │   ├── results.csv
  │   └── process_data.py
  └── papers/
      └── protocol.pdf
```

```python
# 2. Core creates basic Dataset nodes for ALL files
(Dataset {path: "sample1_R1_001.fastq.gz", size: 1.2GB, checksum: "abc123"})
(Dataset {path: "IMG_0001_channel1.tiff", size: 245MB, checksum: "def456"})
(Dataset {path: "results.csv", size: 2MB, checksum: "ghi789"})
(Dataset {path: "process_data.py", size: 15KB, checksum: "jkl012"})
```

```python
# 3. Pattern matcher determines interpreters
PatternMatcher:
  - sample1_R1_001.fastq.gz → IlluminaFASTQInterpreter (pattern match)
  - IMG_0001_channel1.tiff → OMETIFFInterpreter (pattern + sibling file)
  - results.csv → ScientificCSVInterpreter (path pattern)
  - process_data.py → PythonCodeInterpreter (extension)
```

```python
# 4. Interpreters run in their environments and cache results
IlluminaFASTQInterpreter (Python):
  → InterpretationResult {
      status: 'success',
      data: {read_count: 1000000, quality: 'Q30', instrument: 'NovaSeq'}
    }

OMETIFFInterpreter (Bash + exiftool):
  → InterpretationResult {
      status: 'success',
      data: {channels: 4, z_stacks: 20, objective: '60x'}
    }

PythonCodeInterpreter (Python + AST):
  → InterpretationResult {
      status: 'success',
      data: {imports: ['pandas', 'numpy'], functions: ['process_data', 'visualize']}
    }
```

```python
# 5. Knowledge Graph stores interpretations with versioning
MATCH (d:Dataset {checksum: "abc123"})
CREATE (i:Interpretation {
  timestamp: datetime(),
  interpreter_id: "illumina_fastq_v2",
  status: "success",
  data: {read_count: 1000000}
})-[:INTERPRETS]->(d)

# Old interpretations marked as superseded
MATCH (d:Dataset {checksum: "abc123"})-[:HAS_INTERPRETATION]->(old:Interpretation)
WHERE old.timestamp < datetime()
SET old.superseded = true
```

```python
# 6. User queries leverage cached interpretations
User: "Find all Python scripts that use pandas"

# Core queries the knowledge graph efficiently
MATCH (d:Dataset)-[:HAS_INTERPRETATION]->(i:Interpretation)
WHERE 'pandas' IN i.data.imports
RETURN d.path, i.data.functions
```

### Error Handling Example

```python
# Proprietary format encountered
ProprietaryFileInterpreter:
  → InterpretationResult {
      status: 'error',
      errors: [{
        type: 'PROPRIETARY_FORMAT',
        message: 'Requires licensed BioFormat interpreter',
        suggestion: 'Contact vendor for interpreter plugin'
      }]
    }

# Partial interpretation (corrupted file)
CorruptedFASTQInterpreter:
  → InterpretationResult {
      status: 'partial',
      data: {read_count: 45000},  # Got this far
      coverage_percent: 45,
      errors: [{
        type: 'CORRUPT_FILE',
        message: 'File corrupted at byte 4567890',
        severity: 'error'
      }]
    }
```

---

## 5. Implementation & Security

### Creating a New Interpreter

```python
# Option 1: Python interpreter (30 lines)
class VCFInterpreter(FileInterpreter):
    runtime = "python"
    languages = ['.vcf', '.vcf.gz']
    
    def interpret(self, file_path):
        # Parse VCF header
        # Extract variant information
        # Return structured interpretation
        return InterpretationResult(
            status='success',
            data={'variants': count, 'samples': names, 'reference': genome}
        )

# Option 2: Bash interpreter (for tool integration)
#!/bin/bash
FILE="$1"
bcftools stats "$FILE" | grep "number of records" | awk '{print $NF}'

# Option 3: User-defined through UI
# Users write interpreter code in settings page
# System validates in sandbox before saving
```

### Security: Read-Only Sandboxed Execution

```python
class SecureInterpreterExecutor:
    """Sandbox for running user-defined interpreters"""
    
    def __init__(self):
        self.sandbox_config = {
            'read_only': True,               # No file writes
            'network_access': False,          # No external connections
            'max_memory_mb': 512,            # Memory limit
            'max_cpu_seconds': 30,           # Timeout protection
            'allowed_operations': [
                'file_read', 'parse', 'calculate', 'transform'
            ],
            'blocked_operations': [
                'file_write', 'network', 'subprocess', 'eval'
            ]
        }
    
    def execute_interpreter(self, interpreter_code, file_path):
        """Run interpreter in restricted environment"""
        # Create isolated execution context
        # Monitor resource usage
        # Enforce time limits
        # Return results or errors
```

### Adding Major Feature Plugin (More Complex)

```python
# Full plugins remain separate from interpreters
class FacilitySchedulerPlugin(SciDKPlugin):
    # Implement booking system
    # Add calendar UI
    # Create API endpoints
    # Handle complex queries
    # 500+ lines of code
```

---

## 6. Why This Architecture Works

### Clear Separation of Concerns

| Component | Purpose | Complexity | Development Time |
|-----------|---------|------------|------------------|
| **Core** | Infrastructure (filesystem, graph, auth) | High | One-time by core team |
| **Interpreters** | Understand data languages | Low-Medium | 30 min to few hours |
| **Plugins** | Major features (LIMS, PubMed, etc.) | Medium-High | Days to weeks |

### Key Benefits

1. **Polyglot Platform**: Speaks many data languages through interpreters
2. **Flexible Execution**: Interpreters run in Python, Bash, Perl, R environments
3. **Pattern-Based Intelligence**: Smart file matching beyond extensions
4. **Cached Interpretations**: Results stored in knowledge graph with versioning
5. **Safe User Extensions**: Read-only sandboxed execution for custom interpreters
6. **Progressive Enhancement**: Each interpreter adds understanding without breaking others
7. **Clear Mental Model**: 
   - Core = "Infrastructure that finds and tracks files"
   - Interpreters = "Understand what's IN the files"
   - Plugins = "Add major capabilities to the platform"

### User Experience Journey

```
Day 1: Install SciDK
- All files are discoverable ✓
- Basic metadata available ✓
- Can search by name, size, date ✓

Day 2: Configure interpreters for your data
- DICOM files show patient/study info ✓
- FASTQ files reveal sequencing parameters ✓
- Python scripts show dependencies ✓
- Custom formats understood via user interpreters ✓

Week 2: Add plugins for your workflow
- PubMed integration connects papers ✓
- LIMS plugin tracks samples ✓
- Facility scheduler manages instruments ✓

Month 2: Institutional knowledge accumulates
- Cached interpretations speed up queries ✓
- Pattern rules capture institutional practices ✓
- Custom interpreters handle proprietary formats ✓
```

---

## 7. Getting Started

### Minimal Setup
```bash
# Core only - files are discoverable
scidk start

# Built-in interpreters for common formats
scidk enable-interpreter csv
scidk enable-interpreter python
scidk enable-interpreter json

# Add domain-specific interpreters
scidk add-interpreter fastq
scidk add-interpreter dicom
scidk add-interpreter maxquant

# Configure patterns for your lab
scidk configure-patterns --interactive

# Add plugins as needed
scidk install-plugin pubmed
scidk install-plugin lims-connector
```

### For Developers

**Creating an Interpreter** (Staff scientists can do this):
```bash
# Option 1: From template
scidk create-interpreter my-format --runtime python
# Edit interpreter logic
# Test with sample files
# Deploy to team

# Option 2: Through UI
# Settings → Interpreters → Create New
# Choose runtime (Python/Bash/Perl/R)
# Write interpretation logic
# Test and save
```

**Creating a Plugin** (Requires more planning):
```bash
scidk create-plugin my-feature
# Implement full feature with UI/API
# Extensive testing required
# Deploy as complete package
```

### The Polyglot Advantage

SciDK becomes a **universal research data platform** that understands:
- **Scientific formats**: FASTQ, DICOM, FCS, HDF5, NetCDF
- **Analysis outputs**: MaxQuant, QIIME, CellRanger, Seurat
- **Code & notebooks**: Python, R, Jupyter, MATLAB
- **Documents**: PDF, Word, Markdown, LaTeX
- **Semantic data**: RDF, OWL, JSON-LD
- **Proprietary formats**: Via custom interpreters

Each interpreter teaches SciDK another data language, progressively building a comprehensive understanding of your entire research ecosystem.