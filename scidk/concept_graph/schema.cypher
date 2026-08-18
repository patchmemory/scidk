// Concept Graph Schema
// Constraints and indexes for the meta-reasoning layer

// ============================================================================
// Node Constraints
// ============================================================================

// Concept_Tool: Each tool has a unique name
CREATE CONSTRAINT concept_tool_name IF NOT EXISTS
FOR (t:Concept_Tool) REQUIRE t.name IS UNIQUE;

// Concept_Intent: Each intent has a unique name
CREATE CONSTRAINT concept_intent_name IF NOT EXISTS
FOR (i:Concept_Intent) REQUIRE i.name IS UNIQUE;

// Concept_Label: Each label mirror has a unique name
CREATE CONSTRAINT concept_label_name IF NOT EXISTS
FOR (l:Concept_Label) REQUIRE l.name IS UNIQUE;

// Concept_Relationship: Each relationship type has a unique type identifier
CREATE CONSTRAINT concept_relationship_type IF NOT EXISTS
FOR (r:Concept_Relationship) REQUIRE r.type IS UNIQUE;

// ============================================================================
// Indexes for Performance
// ============================================================================

// Index on active tools for planning query performance
CREATE INDEX concept_tool_active IF NOT EXISTS
FOR (t:Concept_Tool) ON (t.active);

// Index on tool source for filtering by MCP vs endpoint vs internal
CREATE INDEX concept_tool_source IF NOT EXISTS
FOR (t:Concept_Tool) ON (t.source);

// Index on label graph_uri for multi-instance deployments
CREATE INDEX concept_label_graph_uri IF NOT EXISTS
FOR (l:Concept_Label) ON (l.graph_uri);

// ============================================================================
// Additional Indexes for Query Performance
// ============================================================================

// Note: Property existence constraints require Neo4j Enterprise Edition.
// In Community Edition, application-level validation enforces required properties.

// Index on intent name for classification query
CREATE INDEX concept_intent_name_idx IF NOT EXISTS
FOR (i:Concept_Intent) ON (i.name);

// Index on relationship type for quick lookups
CREATE INDEX concept_relationship_type_idx IF NOT EXISTS
FOR (r:Concept_Relationship) ON (r.type);
