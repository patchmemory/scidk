# SciDK Interpreter Management System

## Architecture Overview

The Interpreter System allows users to configure how SciDK understands different file types through a flexible, rule-based approach with multiple execution environments.

---

## 1. Interpreter Registry & Configuration

### 1.1 Interpreter Definition Structure

```python
class InterpreterDefinition:
    """Defines an interpreter and its capabilities"""
    
    def __init__(self):
        self.id = "genomics_fastq_v2"
        self.name = "FASTQ Genomics Interpreter"
        self.version = "2.0.1"
        self.author = "user@mit.edu"
        
        # Execution environment
        self.runtime = "python"  # python | bash | perl | node | r
        self.runtime_version = "3.9+"
        
        # What this interpreter can handle
        self.capabilities = {
            "extensions": [".fastq", ".fq", ".fastq.gz"],
            "mime_types": ["text/plain", "application/gzip"],
            "file_patterns": [
                r".*_R[12]_\d{3}\.fastq\.gz$",  # Illumina paired-end
                r".*\.merged\.fastq$"             # Merged reads
            ],
            "max_file_size_mb": 5000,  # Don't attempt files larger than this
            "sampling_strategy": "head"  # head | tail | random | full
        }
        
        # The actual interpretation logic
        self.script_type = "inline"  # inline | file | module
        self.script = """
import gzip
import json

def interpret(file_path, config):
    result = {
        'read_count': 0,
        'read_length': [],
        'quality_scores': [],
        'instrument': None
    }
    
    # Parse first 1000 reads for metadata
    opener = gzip.open if file_path.endswith('.gz') else open
    with opener(file_path, 'rt') as f:
        for i, line in enumerate(f):
            if i >= 4000: break  # 1000 reads
            if i % 4 == 0:  # Header line
                # Parse Illumina header format
                parts = line.strip().split(':')
                if not result['instrument'] and len(parts) >= 7:
                    result['instrument'] = parts[0].replace('@', '')
                result['read_count'] += 1
            elif i % 4 == 1:  # Sequence line
                result['read_length'].append(len(line.strip()))
    
    result['avg_read_length'] = sum(result['read_length']) / len(result['read_length'])
    return result
"""
        
        # Error handling patterns
        self.known_errors = [
            {
                "pattern": "gzip.BadGzipFile",
                "message": "Corrupted GZIP file",
                "severity": "error"
            },
            {
                "pattern": "UnicodeDecodeError",
                "message": "File contains non-text data",
                "severity": "warning"
            }
        ]
```

### 1.2 Bash Interpreter Example

```yaml
# interpreters/tiff_metadata_extractor.yaml
id: tiff_metadata_bash
name: "TIFF Metadata Extractor"
runtime: bash
capabilities:
  extensions: [.tif, .tiff]
  file_patterns:
    - "IMG_\\d{4}_.*\\.tiff?"  # IMG_0001_channel.tif
    - ".*/raw/.*\\.tiff?"       # Any TIFF in raw folder

script: |
  #!/bin/bash
  FILE_PATH="$1"
  
  # Use exiftool to extract metadata
  if command -v exiftool &> /dev/null; then
      # Extract as JSON
      exiftool -json "$FILE_PATH" | jq '{
          width: .ImageWidth,
          height: .ImageHeight,
          bit_depth: .BitsPerSample,
          compression: .Compression,
          software: .Software,
          datetime: .DateTimeOriginal,
          channels: .SamplesPerPixel
      }'
  else
      # Fallback to basic file info
      echo '{"error": "exiftool not installed", "size":'$(stat -f%z "$FILE_PATH")'}'
  fi

dependencies:
  - exiftool
  - jq
```

### 1.3 Pattern-Based Interpreter Rules

```python
class InterpreterRules:
    """User-defined rules for interpreter selection"""
    
    def __init__(self):
        self.rules = [
            {
                "name": "Microscopy TIFFs",
                "priority": 10,
                "conditions": {
                    "path_pattern": r".*/microscopy/.*\.tiff?$",
                    "file_size_mb": ">100",
                    "parent_has_file": "metadata.xml"  # OME-TIFF
                },
                "use_interpreter": "ome_tiff_interpreter",
                "config": {
                    "extract_channels": True,
                    "extract_z_stack": True
                }
            },
            {
                "name": "Analysis CSVs",
                "priority": 5,
                "conditions": {
                    "path_pattern": r".*/analysis/.*\.csv$",
                    "modified_after": "2024-01-01"
                },
                "use_interpreter": "scientific_csv_interpreter",
                "config": {
                    "infer_types": True,
                    "detect_units": True
                }
            },
            {
                "name": "Proprietary Format X",
                "priority": 15,
                "conditions": {
                    "extension": ".propx",
                    "header_bytes": "50524F5058"  # "PROPX" in hex
                },
                "use_interpreter": "custom_propx_interpreter"
            }
        ]
```

---

## 2. Interpreter Management UI

### 2.1 Settings Page Structure

```typescript
// Frontend component for interpreter management
interface InterpreterSettings {
    // Global interpreter settings
    globalSettings: {
        enableAutoDiscovery: boolean;
        maxInterpreterTimeout: number;  // seconds
        cacheInterpretations: boolean;
        parallelExecution: boolean;
        maxParallelJobs: number;
    };
    
    // Per-filetype assignments
    fileTypeAssignments: Map<string, InterpreterAssignment>;
    
    // Pattern-based rules
    patternRules: InterpreterRule[];
    
    // Available interpreters
    availableInterpreters: InterpreterDefinition[];
    
    // User's custom interpreters
    customInterpreters: InterpreterDefinition[];
}

interface InterpreterAssignment {
    extension: string;  // e.g., ".csv"
    primaryInterpreter: string;  // interpreter ID
    fallbackInterpreters: string[];  // ordered list of fallbacks
    enabled: boolean;
    config: any;  // interpreter-specific config
}
```

### 2.2 UI Components

```html
<!-- Interpreter Management Page -->
<div class="interpreter-settings">
    <!-- File Type Assignments -->
    <div class="section">
        <h3>File Type Interpreters</h3>
        <table class="file-type-table">
            <thead>
                <tr>
                    <th>Extension</th>
                    <th>Primary Interpreter</th>
                    <th>Fallback</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>.fastq, .fq</td>
                    <td>
                        <select>
                            <option>FASTQ Genomics v2</option>
                            <option>Basic FASTQ Parser</option>
                            <option>Custom FASTQ Script</option>
                        </select>
                    </td>
                    <td>Text Interpreter</td>
                    <td><span class="status-active">Active</span></td>
                    <td>
                        <button>Configure</button>
                        <button>Test</button>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
    
    <!-- Pattern Rules -->
    <div class="section">
        <h3>Pattern-Based Rules</h3>
        <div class="rules-editor">
            <div class="rule-card">
                <h4>Rule: Microscopy TIFFs</h4>
                <div class="rule-condition">
                    When: Path matches <code>/microscopy/*.tiff</code>
                    AND parent folder has <code>metadata.xml</code>
                </div>
                <div class="rule-action">
                    Use: <strong>OME-TIFF Interpreter</strong>
                </div>
                <div class="rule-priority">Priority: 10</div>
            </div>
        </div>
        <button class="add-rule">+ Add Rule</button>
    </div>
    
    <!-- Custom Interpreter Editor -->
    <div class="section">
        <h3>Create Custom Interpreter</h3>
        <div class="interpreter-editor">
            <input type="text" placeholder="Interpreter Name">
            <select class="runtime-select">
                <option>Python</option>
                <option>Bash</option>
                <option>Perl</option>
                <option>R</option>
            </select>
            <div class="code-editor">
                <textarea placeholder="Write your interpreter script here..."></textarea>
            </div>
            <button>Test with Sample File</button>
            <button>Save Interpreter</button>
        </div>
    </div>
</div>
```

---

## 3. Knowledge Graph Integration

### 3.1 Interpretation Caching Schema

```python
class InterpretationCache:
    """How interpretations are stored in the knowledge graph"""
    
    def cache_interpretation(self, file_path: str, interpretation: dict):
        """Store interpretation with versioning"""
        
        # Create or update Dataset node
        dataset_node = {
            'id': generate_file_id(file_path),
            'path': file_path,
            'checksum': calculate_checksum(file_path),
            'modified': os.path.getmtime(file_path)
        }
        
        # Create Interpretation node with timestamp
        interpretation_node = {
            'id': generate_uuid(),
            'timestamp': datetime.now(),
            'interpreter_id': interpretation['interpreter_id'],
            'interpreter_version': interpretation['version'],
            'status': 'success',  # success | partial | error
            'data': interpretation['result'],
            'errors': interpretation.get('errors', []),
            'warnings': interpretation.get('warnings', []),
            'execution_time_ms': interpretation['exec_time']
        }
        
        # Create relationships
        relationships = [
            ('Dataset', dataset_node['id'], 'HAS_INTERPRETATION', 
             'Interpretation', interpretation_node['id']),
            ('Interpretation', interpretation_node['id'], 'INTERPRETED_BY',
             'Interpreter', interpretation['interpreter_id'])
        ]
        
        # Store in graph with version history
        self.kg.create_or_update(dataset_node)
        self.kg.create(interpretation_node)
        self.kg.create_relationships(relationships)
        
        # Mark old interpretations as superseded
        old_interpretations = self.kg.query("""
            MATCH (d:Dataset {id: $dataset_id})-[:HAS_INTERPRETATION]->(i:Interpretation)
            WHERE i.id <> $new_interpretation_id
            SET i.superseded = true
            """, dataset_id=dataset_node['id'], 
                 new_interpretation_id=interpretation_node['id'])
```

### 3.2 Non-Redundant File Representation

```python
class FileVersioning:
    """Track file changes over time without duplication"""
    
    def track_file(self, file_path: str):
        checksum = calculate_checksum(file_path)
        
        # Check if this exact file version exists
        existing = self.kg.query("""
            MATCH (f:FileVersion {checksum: $checksum})
            RETURN f
            """, checksum=checksum)
        
        if existing:
            # File content unchanged, just update access time
            self.kg.query("""
                MATCH (f:FileVersion {checksum: $checksum})
                SET f.last_seen = datetime()
                """, checksum=checksum)
        else:
            # New version of file
            file_version = {
                'id': generate_uuid(),
                'path': file_path,
                'checksum': checksum,
                'size': os.path.getsize(file_path),
                'created': datetime.now(),
                'last_seen': datetime.now()
            }
            
            # Link to previous versions if they exist
            previous = self.kg.query("""
                MATCH (f:FileVersion {path: $path})
                RETURN f ORDER BY f.created DESC LIMIT 1
                """, path=file_path)
            
            if previous:
                self.kg.create_relationship(
                    file_version['id'], 'SUCCEEDS', previous['id']
                )
```

---

## 4. Error Handling & Partial Interpretation

### 4.1 Interpreter Error Types

```python
class InterpreterError:
    """Standardized error reporting for interpreters"""
    
    ERROR_TYPES = {
        'PARSE_ERROR': 'Failed to parse file format',
        'CORRUPT_FILE': 'File appears to be corrupted',
        'UNSUPPORTED_VERSION': 'File version not supported',
        'PARTIAL_READ': 'Could only read part of file',
        'MISSING_DEPENDENCY': 'Required tool not installed',
        'TIMEOUT': 'Interpretation exceeded time limit',
        'MEMORY_ERROR': 'File too large for available memory',
        'PERMISSION_ERROR': 'Cannot read file (permissions)',
        'PROPRIETARY_FORMAT': 'Proprietary format requires special interpreter'
    }
    
    def __init__(self, error_type: str, details: str, severity: str = 'error'):
        self.type = error_type
        self.details = details
        self.severity = severity  # error | warning | info
        self.timestamp = datetime.now()
```

### 4.2 Partial Interpretation Results

```python
class PartialInterpretation:
    """When we can only understand part of a file"""
    
    def interpret_with_fallback(self, file_path: str):
        result = {
            'status': 'partial',
            'interpreted': {},
            'failed_sections': [],
            'coverage_percent': 0
        }
        
        try:
            # Try primary interpreter
            full_result = self.primary_interpreter.interpret(file_path)
            result['interpreted'] = full_result
            result['status'] = 'success'
            result['coverage_percent'] = 100
            
        except PartialReadError as e:
            # Got some data but not all
            result['interpreted'] = e.partial_data
            result['failed_sections'] = e.failed_sections
            result['coverage_percent'] = e.coverage_percent
            
        except ProprietaryFormatError as e:
            # Need special interpreter
            result['status'] = 'error'
            result['error'] = {
                'type': 'PROPRIETARY_FORMAT',
                'message': f'Format requires: {e.required_interpreter}',
                'suggestion': f'Install interpreter: {e.install_command}'
            }
            
        return result
```

---

## 5. Standard Interpreter Library

### 5.1 Built-in Interpreters for Common Formats

```yaml
# Standard library of interpreters
standard_library:
  structured_data:
    - json_interpreter:
        handles: [.json, .jsonl]
        features: [schema_inference, validation, json_path]
    
    - xml_interpreter:
        handles: [.xml]
        features: [xpath, schema_validation, namespace_handling]
    
    - yaml_interpreter:
        handles: [.yaml, .yml]
        features: [multi_document, references, schema_validation]
  
  semantic_formats:
    - rdf_interpreter:
        handles: [.rdf, .ttl, .n3]
        features: [triple_extraction, ontology_detection, sparql_ready]
    
    - owl_interpreter:
        handles: [.owl]
        features: [class_hierarchy, property_extraction, reasoning_support]
  
  scientific_data:
    - hdf5_interpreter:
        handles: [.h5, .hdf5]
        features: [dataset_listing, attribute_extraction, group_navigation]
    
    - netcdf_interpreter:
        handles: [.nc, .nc4]
        features: [dimension_extraction, variable_metadata, coordinate_systems]
```

### 5.2 Configurable Interpreter Features

```python
class ConfigurableInterpreter:
    """Base class for interpreters with optional features"""
    
    def __init__(self, config: dict):
        self.features = {
            'extract_metadata': config.get('extract_metadata', True),
            'parse_content': config.get('parse_content', False),
            'infer_schema': config.get('infer_schema', True),
            'validate': config.get('validate', False),
            'extract_links': config.get('extract_links', True),
            'sample_size': config.get('sample_size', 1000)
        }
    
    def interpret(self, file_path: str):
        result = {}
        
        if self.features['extract_metadata']:
            result['metadata'] = self.extract_metadata(file_path)
        
        if self.features['parse_content']:
            result['content'] = self.parse_content(
                file_path, 
                limit=self.features['sample_size']
            )
        
        if self.features['infer_schema']:
            result['schema'] = self.infer_schema(result.get('content', []))
        
        return result
```

---

## 6. Security & Sandboxing

### 6.1 Read-Only Execution Environment

```python
class SecureInterpreterExecutor:
    """Sandbox for running user-defined interpreters"""
    
    def __init__(self):
        self.sandbox_config = {
            'read_only': True,
            'network_access': False,
            'max_memory_mb': 512,
            'max_cpu_seconds': 30,
            'allowed_imports': [
                'json', 'csv', 'xml', 're', 'datetime',
                'pandas', 'numpy'  # Pre-approved libraries
            ],
            'blocked_operations': [
                'open(.*"w".*)',  # No write mode
                'subprocess',      # No system calls
                'eval', 'exec',    # No dynamic execution
                '__import__'       # No dynamic imports
            ]
        }
    
    def execute_interpreter(self, interpreter_code: str, file_path: str):
        """Run interpreter in sandboxed environment"""
        
        # Create restricted globals
        safe_globals = {
            '__builtins__': self.create_safe_builtins(),
            'file_path': file_path,
            'read_file': self.safe_read_file,
            'parse_json': json.loads,
            'parse_csv': self.safe_csv_parser
        }
        
        # Execute with resource limits
        with self.resource_limiter():
            result = exec(interpreter_code, safe_globals)
            
        return result
```

---

## 7. Usage Example

```python
# User defines a custom interpreter for their proprietary format
custom_interpreter = """
# Interpreter for our lab's custom .labdata format
import struct

def interpret(file_path, config):
    with open(file_path, 'rb') as f:
        # Read header
        magic = f.read(4)
        if magic != b'LABD':
            raise ValueError('Not a valid .labdata file')
        
        version = struct.unpack('I', f.read(4))[0]
        num_samples = struct.unpack('I', f.read(4))[0]
        
        # Read metadata section
        metadata_size = struct.unpack('I', f.read(4))[0]
        metadata = json.loads(f.read(metadata_size))
        
        return {
            'format_version': version,
            'sample_count': num_samples,
            'experiment_id': metadata.get('experiment_id'),
            'researcher': metadata.get('researcher'),
            'date': metadata.get('date'),
            'parameters': metadata.get('parameters', {})
        }
"""

# Register and use
scidk.register_interpreter(
    name="Lab Data Format",
    runtime="python",
    extensions=[".labdata"],
    code=custom_interpreter
)

# Now all .labdata files will be automatically interpreted
```

This system provides the flexibility you need while maintaining security through read-only sandboxing and comprehensive error handling. Users can create interpreters in their preferred language, apply them selectively based on patterns, and all results are efficiently cached in the knowledge graph.