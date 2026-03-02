# ---
# id: sample_to_imagingdataset
# name: Sample → ImagingDataset by path matching
# version: 1.0.0
# format: cypher
# description: Links Sample nodes to ImagingDataset nodes where sample_id appears in dataset path
# from_label: Sample
# to_label: ImagingDataset
# relationship_type: SUBJECT_OF
# matching_strategy: exact
# idempotent: true
# ---

MATCH (s:Sample)
MATCH (img:ImagingDataset)
WHERE toLower(img.path) CONTAINS toLower(s.sample_id)
MERGE (s)-[r:SUBJECT_OF]->(img)
SET r.linked_by = 'sample_to_imagingdataset',
    r.linked_at = timestamp()
RETURN count(r) as created
