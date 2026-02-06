"""
Flask blueprints for SciDK web routes.

This package organizes routes into logical blueprints:
- ui: User-facing HTML pages
- api_files: File/scan/dataset operations
- api_graph: Graph schema and visualization
- api_tasks: Background task management
- api_chat: Chat/LLM interface
- api_neo4j: Neo4j integration and commit operations
- api_admin: Health, metrics, logs
- api_interpreters: Interpreter configuration
- api_providers: Filesystem provider management
- api_annotations: Annotations and relationships management

All blueprints are registered in create_app() in scidk/web/__init__.py
"""

def register_blueprints(app):
    """
    Register all route blueprints with the Flask app.

    This function is called from create_app() after initializing
    core extensions (graph, registry, filesystem manager, etc.)
    """
    # Import blueprints (deferred to avoid circular imports)
    from . import ui
    from . import api_files
    from . import api_graph
    from . import api_tasks
    from . import api_chat
    from . import api_neo4j
    from . import api_admin
    from . import api_interpreters
    from . import api_providers
    from . import api_annotations
    from . import api_labels
    from . import api_links
    from . import api_integrations
    from . import api_settings

    # Register UI blueprint
    app.register_blueprint(ui.bp)

    # Register API blueprints
    app.register_blueprint(api_files.bp)
    app.register_blueprint(api_graph.bp)
    app.register_blueprint(api_tasks.bp)
    app.register_blueprint(api_chat.bp)
    app.register_blueprint(api_neo4j.bp)
    app.register_blueprint(api_admin.bp)
    app.register_blueprint(api_interpreters.bp)
    app.register_blueprint(api_providers.bp)
    app.register_blueprint(api_annotations.bp)
    app.register_blueprint(api_labels.bp)
    app.register_blueprint(api_integrations.bp)
    app.register_blueprint(api_links.bp)  # Keep for backward compatibility
    app.register_blueprint(api_settings.bp)
