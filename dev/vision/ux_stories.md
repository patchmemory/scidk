# SciDK User Experience Stories
## Science Data Kit: Where Scientists Do Science with Data

*Not just an SDK (Software Development Kit), but a SciDK (Science Data Kit) - built by scientists, for scientists, to make data as easy to work with as pipettes and microscopes.*

---

## Vision: Your Research Assistant That Never Forgets

SciDK transforms scattered research data into connected, conversational knowledge. Ask questions in plain English. Get answers that span your entire research ecosystem - from raw microscopy images to published papers, from gene sequences to animal protocols.

---

## Core User Stories

### Story 1: The Morning Research Planning Session
**As a researcher planning new experiments**  
**I want to** quickly find all relevant prior work and protocols  
**So that I** don't duplicate experiments and can build on existing knowledge  

#### The Experience:

**Dr. Sarah (9:00 AM)**: *"I'm planning a lung cancer study with EGFR mutations. What protocols and prior work should I know about?"*

**SciDK responds**:
```
Found relevant resources across your institute:

📋 PROTOCOLS & SOPs (3 matches):
• SOP-2024-LC-001: "EGFR Mutation Detection in Lung Tissue" 
  - Preclinical Imaging Core, validated March 2024
  - Used in 47 experiments, 94% success rate
  [View Protocol] [See Results from These Experiments]

• IACUC Protocol #2023-089: "Orthotopic Lung Cancer Models"
  - Approved for your lab through Dec 2024
  - Allows up to 40 mice, intratracheal injection
  [View Full Protocol] [Check Current Usage: 22/40 mice]

🔬 PREVIOUS EXPERIMENTS (8 datasets):
• Laura M's 2024 Q1 Study (MIT_2024_PCI_003)
  - 127 microCT scans of EGFR+ tumors
  - Linked to NC3Rs EDA design #4521
  - Key finding: "Tumors visible at day 7 post-injection"
  [Explore Data] [View EDA Design] [Contact Laura]

📚 LITERATURE CONNECTIONS (12 papers):
• Chen et al. 2024: "EGFR targeting in orthotopic models"
  - Cites similar protocol to SOP-2024-LC-001
  - Reports 85% tumor take rate
  [Read Paper] [Compare Methods]

💡 SUGGESTED EXPERIMENTAL DESIGN:
Based on similar studies, consider:
- Sample size: n=8-10 per group (from NC3Rs power analysis)
- Timeline: Image at days 7, 14, 21 (from Laura's optimization)
- Controls: Use littermate controls (per IACUC requirement)
[Generate NC3Rs EDA Draft] [Book Imaging Slots]
```

**Value**: Sarah saves 3 hours of searching and avoids duplicating Laura's optimization work.

---

### Story 2: The Multi-Modal Data Integration Challenge
**As a researcher with data from multiple core facilities**  
**I want to** see connections across all my different data types  
**So that I** can discover patterns that lead to breakthroughs  

#### The Experience:

**Dr. James (2:00 PM)**: *"Show me all the genomics and imaging data from yesterday's experiment batch"*

**SciDK integrates across facilities**:
```
Yesterday's Data for Experiment Batch EXP-2024-11-07:

🧬 GENOMICS (Koch Genomics Core):
• 16S rRNA Sequencing completed 14:30
  - 24 samples, mouse gut microbiome
  - OTU table: 847 unique OTUs identified
  - Top taxa: Bacteroides (34%), Lactobacillus (28%)
  - Quality: All samples passed QC (>50k reads)
  [View OTU Table] [Interactive Taxonomy Browser] [Compare to Baseline]

🔬 IMAGING (Preclinical Imaging Core):
• MicroCT Session 15:45 (Operator: Milton)
  - 12 mice scanned, lung protocol
  - Data location: /imaging/2024/11/07/microCT/
  - Preliminary finding: 3 mice show nodules
  [View Images] [Download DICOM] [Request Analysis]

🧪 FLOW CYTOMETRY (Your Lab):
• Tumor dissociation processed 16:00
  - 12 samples, standard immune panel
  - CD8+ T cells: Mean 18.3% (range 12-24%)
  [View FCS Files] [Gating Strategy]

📊 CROSS-MODAL INSIGHTS:
• Mice #3, #7, #9 with visible nodules show highest CD8+ infiltration
• These same mice have altered gut microbiome (↑ Akkermansia)
• Similar pattern reported in Wang et al. 2023 (anti-PD1 responders)
[Generate Correlation Matrix] [Export Combined Dataset]
```

**Value**: James discovers a multi-modal biomarker signature he would have missed looking at each dataset separately.

---

### Story 3: The Literature-to-Bench Connection
**As a researcher comparing my data to published work**  
**I want to** instantly see how my results relate to the literature  
**So that I** can validate findings and identify novel discoveries  

#### The Experience:

**Postdoc Maria (3:30 PM)**: *"How does our gut microbiome profile compare to published anti-PD1 responder signatures?"*

**SciDK connects data to literature**:
```
Comparing your OTU data to published signatures:

📊 YOUR DATA vs. PUBLISHED SIGNATURES:

Matching "Anti-PD1 Responder" Signatures:
1. Gopalakrishnan et al. 2018 (Science)
   - Similarity: 72% (based on genus-level composition)
   - Key overlap: ↑ Akkermansia, ↑ Faecalibacterium
   - Missing in your data: Ruminococcus (not detected)
   
2. Jin et al. 2019 (Nat Med)
   - Similarity: 81% (best match!)
   - Both show Bacteroides/Prevotella ratio >1.5

🧬 TAXONOMIC DEEP DIVE:
Your Akkermansia muciniphila (OTU_00034):
- Abundance: 8.3% (responders), 0.4% (non-responders)
- 99.2% identity to NCBI Reference NR_074436.1
- Also elevated in 3 other MIT studies:
  • Smith Lab 2023: Checkpoint inhibitor study
  • Jones Lab 2024: CAR-T response correlation
  [View Phylogenetic Tree] [BLAST Against MIT Database]

💡 SUGGESTED NEXT STEPS:
1. Validate Akkermansia by qPCR (SOP available)
2. Consider fecal transfer experiment (see IACUC #2023-091)
3. Check if Smith Lab has frozen samples for comparison
[Draft Validation Plan] [Contact Smith Lab]
```

**Value**: Maria's finding is immediately validated against literature, accelerating publication by months.

---

### Story 4: The Grant Progress Synthesis
**As a PI managing multiple grants**  
**I want to** automatically track progress against specific aims  
**So that I** can focus on science, not administrative reporting  

#### The Experience:

**PI Dr. Johnson (5:00 PM)**: *"Create a summary connecting all of today's work to our grant aims"*

**SciDK synthesizes across all systems**:
```
PROJECT SYNTHESIS: R01-CA-246810 Aim 2 Progress

Today's Integrated Findings:

🎯 GRANT AIM 2: "Identify microbiome signatures predicting immunotherapy response"

PROGRESS UPDATE:
✅ Milestone 2.1: Establish baseline microbiome (COMPLETE)
  - 24 samples processed (target was 20)
  - OTU identification complete
  - Data in: /genomics/2024/grant_R01CA246810/baseline/

⚡ KEY FINDING: 
Your Akkermansia enrichment (8.3% in responders) exceeds the 
threshold (5%) proposed in your grant. This strengthens your 
hypothesis about gut-lung axis in immunotherapy.

📊 SUPPORTING DATA:
• Imaging: 3/12 mice with both tumors AND high Akkermansia
• Flow: Same mice show CD8+ infiltration (p=0.003)
• Literature: 81% match to Jin et al. responder signature
• NC3Rs EDA: Power calculation confirmed (n=8 sufficient)

📋 COMPLIANCE STATUS:
• IACUC Protocol: 22/40 mice used (55%)
• Core Facility Hours: Genomics (18/50), Imaging (8/30)
• Data Management: All data FAIR-compliant, archived

📎 AUTOMATED OUTPUTS:
[Generate Progress Report] [Update NC3Rs] [Export to NIH Format]
[Schedule Core Facilities] [Order Reagents] [Draft Figure 1]
```

**Value**: Dr. Johnson saves 2 hours on progress reporting and identifies a key finding for the next publication.

---

### Story 5: The New Lab Member Onboarding
**As a new postdoc joining a lab**  
**I want to** quickly understand what work has been done before  
**So that I** can build on existing knowledge from day one  

#### The Experience:

**New Postdoc Alex (Day 3)**: *"What lung cancer work has been done in this lab? What methods worked best?"*

**SciDK provides institutional memory**:
```
Lab History: Lung Cancer Research (2019-2024)

📚 KNOWLEDGE SUMMARY:
• 12 completed projects, 487 experiments total
• 3 published papers, 2 in preparation
• 1,247 GB data archived, all searchable

🏆 SUCCESSFUL PROTOCOLS:
1. Orthotopic injection (Laura's optimization)
   - Success rate improved from 45% → 94%
   - Key: Use 30G needle, inject slowly (30 seconds)
   - See video: Laura_injection_technique_2023.mp4

2. MicroCT tumor detection
   - Optimal: Day 7, 14, 21 post-injection
   - Settings: 90kV, 88µA, 0.5mm Al filter
   - Analysis pipeline: /shared/scripts/tumor_segmentation_v3.py

❌ WHAT DIDN'T WORK (save time!):
• Subcutaneous model: Poor translation to human
• Daily imaging: Too stressful for mice, affected growth
• Protocol v1.0 cell prep: 60% viability (v2.0: 95%)

👥 EXPERT CONTACTS:
• Laura M: Orthotopic injections, imaging (last active: today)
• Dr. Chen: CRISPR screens (moved to Stanford, happy to help)
• Milton: MicroCT wizard (office: Room 76-553)

📂 STARTING RESOURCES:
[Download Starter Pack] [View Training Videos] [Shadow Laura Next Week]
```

**Value**: Alex achieves in 3 days what usually takes 3 months of knowledge gathering.

---

### Story 6: The Core Facility Intelligence Amplification
**As a core facility manager**  
**I want to** turn my expertise into searchable institutional knowledge  
**So that** users get answers instantly and I can focus on complex problems  

#### The Experience:

**Milton, MicroCT Specialist**: *"SciDK, someone's asking about imaging lung tumors in black mice. What's worked before?"*

**SciDK leverages facility knowledge**:
```
Imaging Black Mice: Facility Knowledge Base

🔬 PREVIOUS CASES (3 similar):
1. Project MIT_2022_187 (Dr. Kim's lab)
   - Challenge: Poor contrast in C57BL/6 mice
   - Solution: Increased exposure time 3x, adjusted kV to 70
   - Result: Successfully imaged 24 mice
   
2. Project MIT_2023_045 (Dr. Patel's lab)
   - Used contrast agent: Fenestra VC
   - Timing: Inject 2hr before imaging
   - Dose: 0.1 mL per 25g body weight

📋 RECOMMENDED PROTOCOL:
For black mice (C57BL/6) lung tumors:
• Settings: 70kV, 114µA, 1mm Al filter
• Exposure: 3x standard (300ms vs 100ms)
• Consider contrast agent for tumors <2mm
• Book extra time slot (45min vs standard 15min)

💡 MILTON'S NOTES (auto-extracted):
"Black mice absorb more X-rays due to melanin in skin.
Compensate with longer exposure or contrast agent.
Never had success with tumors <1mm without contrast."

📊 SUCCESS METRICS:
• 87% successful tumor detection with this protocol
• Average tumor size detected: 1.8mm
• 28 successful projects using this approach

[Generate Protocol PDF] [Book Extended Session] [Order Contrast Agent]
```

**Value**: Milton's expertise becomes institutional infrastructure, available 24/7.

---

## Plugin Developer Story

### Story 7: The Staff Scientist as Plugin Developer
**As a staff scientist with domain expertise**  
**I want to** create a plugin for my facility without deep programming knowledge  
**So that** our specialized data integrates with the institute's SciDK  

#### The Experience:

**Dr. Alex, Mass Spec Facility (Monday morning)**:

```bash
# Step 1: Create plugin from template (2 minutes)
$ scidk create-plugin mass-spec-core
> Plugin display name: Mass Spectrometry Core
> Your GitHub username: alex-scientist
> Data types: proteomics, metabolomics
✅ Created: scidk-plugin-mass-spec-core/

# Step 2: Open in Cursor AI editor
$ cd scidk-plugin-mass-spec-core
$ cursor .
```

**In Cursor, Alex writes a comment**:
```python
# TODO: Parse MaxQuant output files with protein IDs, abundance, and link to UniProt
```

**Cursor AI generates the complete parser code**:
```python
def parse_maxquant(self, filepath: Path) -> Dict[str, Any]:
    """Parse MaxQuant proteinGroups.txt output"""
    df = pd.read_csv(filepath, sep='\t')
    
    proteins = []
    for _, row in df.iterrows():
        protein = {
            'protein_id': row.get('Protein IDs', ''),
            'gene_name': row.get('Gene names', ''),
            'uniprot_id': self._extract_uniprot_id(row.get('Protein IDs', '')),
            'sequence_coverage': row.get('Sequence coverage [%]', 0),
            'unique_peptides': row.get('Unique peptides', 0)
        }
        if protein['unique_peptides'] >= 2:  # Standard threshold
            proteins.append(protein)
    
    return {'proteins': proteins}
```

**30 minutes later, the plugin is working**:
- ✅ Parses facility's data formats
- ✅ Connects to knowledge graph
- ✅ Handles natural language queries
- ✅ Links to UniProt automatically

**User can now ask**: *"Show proteins identified in yesterday's mass spec run"*

**Value**: Alex creates in half a day what would have taken weeks of development.

---

## The "Aha!" Moments

### For Researchers
1. **"Wait, Laura already optimized this protocol?"** - Discovering internal work before wasting months
2. **"Our microbiome matches that Nature paper?"** - Instant validation against literature
3. **"All three datasets point to the same mice?"** - Multi-modal patterns emerge
4. **"It drafted my progress report?"** - Automatic compliance documentation

### for PIs
1. **"I can see all my lab's work instantly"** - No more knowledge walking out the door
2. **"My students found the protocol themselves"** - Self-service knowledge access
3. **"We're already 80% toward Aim 2?"** - Real-time grant progress tracking

### For Core Facilities
1. **"Users stopped asking the same questions"** - Expertise becomes searchable
2. **"They're using the optimal protocol now"** - Best practices self-propagate
3. **"I can see usage patterns across the institute"** - Data-driven facility planning

### For Graduate Students
1. **"I found all related work in 5 minutes"** - Comprehensive literature + data search
2. **"I know exactly who to ask for help"** - Expert network discovery
3. **"My thesis committee loves my organization"** - Professional data management from day one

---

## The SciDK Difference

### Traditional Approach
- 40% of time searching for data
- Knowledge leaves with people
- Experiments unnecessarily repeated
- Connections missed between datasets
- Compliance is painful documentation

### With SciDK
- Ask questions, get answers instantly
- Knowledge accumulates permanently
- Build on validated protocols
- AI discovers hidden patterns
- Compliance happens automatically

---

## Implementation Philosophy

**SciDK is not about data management.**  
**It's about scientific discovery.**

Every feature is designed to help scientists do science:
- Natural language, not database queries
- Answers span all your data sources
- Works with your existing tools
- Grows smarter with every use
- Makes you look brilliant (because you are)

---

## The Bottom Line

SciDK transforms your institute's scattered data into a unified intelligence layer that makes every researcher more effective, every discovery more likely, and every collaboration more powerful.

**For Scientists**: Stop hunting for data. Start discovering insights.  
**For Institutes**: Turn data chaos into competitive advantage.  
**For Science**: Accelerate discovery by connecting all knowledge.

*Built by scientists who were tired of losing data.*  
*For scientists who want to do science, not data management.*

---

## Getting Started

```bash
# For users: Just ask questions
"Show me all lung cancer data from the last year"

# For developers: Create plugins with AI help
scidk create-plugin my-facility

# For institutes: Deploy in phases
Start with willing early adopters → Scale to entire facility → Connect to other institutes
```

Welcome to SciDK - where your data finally works as hard as you do.