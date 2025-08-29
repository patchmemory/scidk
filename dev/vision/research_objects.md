# RO-Crate as Native Dataset Collection in SciDK File Browser

## The Concept: RO-Crate as Living Research Objects

Instead of loose files, users work with **Research Objects** (RO-Crates) as the primary organizational unit in SciDK.

```
┌─────────────────────────────────────────────────────────────┐
│                 SciDK File Browser                          │
│                                                             │
│  📁 Research Objects (RO-Crates)                           │
│  ├── 🔬 Laura's Lung Cancer Study                          │
│  │   ├── 📊 microscopy/                                    │
│  │   ├── 🧬 genomics/                                      │
│  │   ├── 📝 analysis_scripts/                             │
│  │   └── 📋 ro-crate-metadata.json                        │
│  │                                                         │
│  ├── 🔬 Tom's Protein Analysis                             │
│  │   ├── 📊 mass_spec_data/                               │
│  │   ├── 📈 results/                                      │
│  │   └── 📋 ro-crate-metadata.json                        │
│  │                                                         │
│  └── 📂 Unorganized Files (to be added to RO-Crates)      │
│      ├── random_data.csv                                   │
│      └── temp_analysis.py                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## User Experience: Building Research Objects

### **1. Create New Research Object**
```javascript
// User clicks "New Research Object" 
const newRO = {
  "@context": "https://w3id.org/ro/crate/1.1/context",
  "@graph": [
    {
      "@type": "CreativeWork",
      "@id": "ro-crate-metadata.json",
      "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
      "about": {"@id": "./"}
    },
    {
      "@type": "Dataset",
      "@id": "./",
      "name": "New Research Object",
      "author": {"@id": "#current-user"},
      "dateCreated": "2024-08-19",
      "hasPart": []  // Files will be added here
    }
  ]
}
```

### **2. Drag-and-Drop File Collection**
```html
<!-- File Browser UI -->
<div class="research-objects-panel">
  <div class="ro-crate" data-ro-id="laura-lung-cancer">
    <h3>🔬 Laura's Lung Cancer Study</h3>
    <div class="file-count">23 files, 487GB</div>
    <div class="drop-zone">
      Drop files here to add to research object
    </div>
  </div>
</div>

<div class="files-panel">
  <div class="file-item draggable" data-path="/data/new_experiment.csv">
    📊 new_experiment.csv (2.3MB)
  </div>
</div>
```

### **3. Live RO-Crate Building**
```python
# As user adds files, update the RO-Crate in real-time
class LiveROCrateBuilder:
    def add_file_to_research_object(self, ro_id, file_path):
        """Add file to existing RO-Crate"""
        
        # Get current RO-Crate from Neo4j
        ro_crate = self.neo4j.get_ro_crate(ro_id)
        
        # Get file interpretation
        interpretation = self.interpreters.process_file(file_path)
        
        # Add file to RO-Crate graph
        file_entity = {
            "@type": "File", 
            "@id": f"./{Path(file_path).name}",
            "name": Path(file_path).name,
            "contentSize": interpretation.get('size_bytes'),
            "encodingFormat": interpretation.get('mime_type'),
            "description": interpretation.get('description'),
            
            # Your interpreter metadata
            "additionalProperty": [
                {"@type": "PropertyValue", "name": k, "value": v}
                for k, v in interpretation.get('metadata', {}).items()
            ]
        }
        
        # Update RO-Crate
        ro_crate['@graph'].append(file_entity)
        
        # Add to hasPart relationship
        root_dataset = next(item for item in ro_crate['@graph'] 
                           if item.get('@id') == './')
        root_dataset['hasPart'].append({"@id": file_entity['@id']})
        
        # Store back in Neo4j
        self.neo4j.update_ro_crate(ro_id, ro_crate)
        
        return ro_crate
```

---

## UI Integration with Existing Tools

### **Embed Crate-O for Metadata Editing**
```html
<!-- When user clicks "Edit Metadata" on a research object -->
<div class="ro-crate-editor-modal">
  <h2>Edit Research Object: Laura's Lung Cancer Study</h2>
  
  <!-- Embed Crate-O component -->
  <div id="crate-o-editor"></div>
  
  <script>
    import { CrateEditor } from '@language-research-technology/crate-o'
    
    const editor = new CrateEditor({
      target: document.getElementById('crate-o-editor'),
      props: { 
        crate: currentROCrateData,
        mode: sciDKProfile  // Custom profile for scientific data
      }
    })
    
    // Save changes back to SciDK
    editor.on('save', (updatedCrate) => {
      fetch('/api/ro-crates/' + roId, {
        method: 'PUT',
        body: JSON.stringify(updatedCrate)
      })
    })
  </script>
</div>
```

### **Smart File Suggestions**
```python
class SmartROCrateBuilder:
    def suggest_files_for_research_object(self, ro_id):
        """AI-powered suggestions for files to add"""
        
        ro_crate = self.neo4j.get_ro_crate(ro_id)
        
        # Analyze existing files in RO-Crate
        existing_keywords = self.extract_keywords(ro_crate)
        existing_file_types = self.get_file_types(ro_crate)
        
        # Find related files using Neo4j graph queries
        suggestions = self.neo4j.query("""
        MATCH (f:File)
        WHERE NOT f.path IN $existing_files
        AND (
          any(keyword in f.keywords WHERE keyword IN $keywords)
          OR f.file_type IN $file_types
          OR f.author = $current_author
        )
        RETURN f.path, f.name, f.description
        ORDER BY similarity_score DESC
        LIMIT 10
        """, {
            'existing_files': [f['@id'] for f in ro_crate['@graph'] if f.get('@type') == 'File'],
            'keywords': existing_keywords,
            'file_types': existing_file_types,
            'current_author': ro_crate.get('author', {}).get('@id')
        })
        
        return suggestions
```

---

## Backend Architecture

### **RO-Crate as First-Class Citizens**
```python
# scidk/core/research_objects.py
class ResearchObjectManager:
    """Manage RO-Crates as the primary organizational unit"""
    
    def __init__(self, neo4j_adapter):
        self.neo4j = neo4j_adapter
        
    def create_research_object(self, name, author_id, description=""):
        """Create new RO-Crate"""
        
        ro_crate = {
            "@context": "https://w3id.org/ro/crate/1.1/context",
            "@graph": [
                {
                    "@type": "CreativeWork",
                    "@id": "ro-crate-metadata.json",
                    "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                    "about": {"@id": "./"}
                },
                {
                    "@type": "Dataset",
                    "@id": "./",
                    "name": name,
                    "description": description,
                    "author": {"@id": author_id},
                    "dateCreated": datetime.now().isoformat(),
                    "hasPart": [],
                    "license": {"@id": "https://creativecommons.org/licenses/by/4.0/"}
                }
            ]
        }
        
        # Store in Neo4j as connected graph
        ro_id = self.neo4j.import_ro_crate(ro_crate)
        return ro_id, ro_crate
    
    def list_research_objects(self, user_id):
        """List all RO-Crates accessible to user"""
        return self.neo4j.query("""
        MATCH (ro:Dataset)-[:AUTHORED_BY]->(user:Person {id: $user_id})
        WHERE ro.conformsTo CONTAINS "ro/crate"
        RETURN ro.id, ro.name, ro.description, ro.dateCreated,
               size((ro)-[:HAS_PART]->()) as file_count
        ORDER BY ro.dateCreated DESC
        """, user_id=user_id)
    
    def add_file_to_ro(self, ro_id, file_path):
        """Add interpreted file to RO-Crate"""
        # Implementation from above
        pass
        
    def export_ro_crate(self, ro_id, format='zip'):
        """Export RO-Crate as downloadable package"""
        
        # Get RO-Crate metadata from Neo4j  
        ro_crate = self.neo4j.get_ro_crate(ro_id)
        
        if format == 'zip':
            # Create ZIP file with ro-crate-metadata.json + all files
            return self.create_zip_package(ro_crate)
        elif format == 'bagit':
            # Create BagIt package
            return self.create_bagit_package(ro_crate)
        elif format == 'json':
            # Just return the JSON-LD metadata
            return ro_crate
```

### **Flask Routes**
```python
# scidk/web/routes/research_objects.py
@app.route('/api/research-objects', methods=['POST'])
def create_research_object():
    data = request.json
    ro_id, ro_crate = ro_manager.create_research_object(
        name=data['name'],
        author_id=session['user_id'],
        description=data.get('description', '')
    )
    return jsonify({'id': ro_id, 'ro_crate': ro_crate})

@app.route('/api/research-objects/<ro_id>/files', methods=['POST'])
def add_file_to_research_object(ro_id):
    file_path = request.json['file_path']
    updated_ro = ro_manager.add_file_to_ro(ro_id, file_path)
    return jsonify(updated_ro)

@app.route('/api/research-objects/<ro_id>/export')
def export_research_object(ro_id):
    format = request.args.get('format', 'zip')
    package = ro_manager.export_ro_crate(ro_id, format)
    
    if format == 'zip':
        return send_file(package, as_attachment=True, 
                        download_name=f'research_object_{ro_id}.zip')
    else:
        return jsonify(package)
```

---

## Benefits of This Approach

### **1. Standards-Native Organization**
- Users naturally build FAIR Digital Objects
- No custom "project" or "dataset" concepts to learn
- Direct export to any repository that accepts RO-Crates

### **2. Progressive Enhancement** 
- Start with simple file collection
- Add metadata as needed using embedded Crate-O
- Gradually build richer research objects

### **3. Interoperability By Default**
- RO-Crates work with Dataverse, WorkflowHub, Zenodo
- Users can move research objects between systems
- Standard JSON-LD for maximum compatibility

### **4. Smart Assistance**
```javascript
// Smart suggestions as user builds research objects
"Based on the files you've added, consider including:"
- "📊 analysis_results.csv (matches your protein analysis theme)"
- "🔬 protocol_v2.pdf (authored by same researcher)" 
- "📝 README.md (to document your workflow)"
```

### **5. Version Control for Research Objects**
```python
# Track evolution of research objects
ro_crate_v1 = "Initial data collection"
ro_crate_v2 = "Added analysis scripts" 
ro_crate_v3 = "Final publication version"

# Neo4j naturally tracks these relationships
```

---

## Implementation Priority

1. **Week 1**: Basic RO-Crate creation and file addition
2. **Week 2**: File browser UI with drag-and-drop
3. **Week 3**: Embed Crate-O for metadata editing
4. **Week 4**: Smart file suggestions and export options

This makes RO-Crate your **native research organization method**, not just an export format. Users build standards-compliant research objects naturally through normal file management activities.