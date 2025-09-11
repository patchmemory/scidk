import inspect
import scidk.app as appmod


def test_commit_neo4j_uses_two_stage_folder_queries():
    # Ensure the function contains both upsert and link Cypher templates
    src = inspect.getsource(appmod.commit_to_neo4j_batched)
    assert "folders_upsert_cql" in src
    assert "folders_link_cql" in src
    # Upsert CQL must set Folder with host and attach SCANNED_IN
    assert "MERGE (fo:Folder" in src and ":SCANNED_IN" in src
    # Link CQL must connect parent->child
    assert "MERGE (child:Folder" in src and "(parent)-[:CONTAINS]->(child)" in src
