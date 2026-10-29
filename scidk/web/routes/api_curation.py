"""Default-off human review API. No agent tools or automatic materialization."""
import os

from flask import Blueprint, current_app, jsonify, request
from ...curation.auth import AuthenticationError, request_reviewer
from ...curation.contracts import ConflictError, ContractError
from ...curation.review import AuthorizationError

bp = Blueprint('api_curation', __name__, url_prefix='/api/curation')


def register_curation(app):
    if app.config.get('SCIDK_CURATION_ENABLED', os.environ.get('SCIDK_CURATION_ENABLED', '0')) in (True, '1'):
        app.register_blueprint(bp)


@bp.before_request
def authorize_request():
    try:
        reviewer = request_reviewer()
        service = current_app.extensions.get('curation_review')
        if service is None:
            return jsonify(error='Curation service is not configured'), 503
        service.authorize(reviewer)
        from flask import g
        g.curation_reviewer = reviewer
    except AuthenticationError:
        return jsonify(error='Named human authentication required'), 401
    except AuthorizationError:
        return jsonify(error='Named authorized human session required'), 403
    except Exception:
        current_app.logger.exception('Curation authorization unavailable')
        return jsonify(error='Curation authorization unavailable'), 503


def _call(function):
    from flask import g
    service = current_app.extensions['curation_review']
    try:
        result = function(service, g.curation_reviewer)
        if request.endpoint == 'api_curation.review':
            from ...core.auth import get_auth_manager
            auth = get_auth_manager(db_path=current_app.config.get('SCIDK_SETTINGS_DB', 'scidk_settings.db'))
            try:
                user = auth.get_user(int(g.curation_reviewer))
                auth.log_audit(user['username'], 'curation_review',
                               details=result['decision_id'], ip_address=request.remote_addr)
            finally:
                auth.close()
        return jsonify(result)
    except AuthorizationError:
        return jsonify(error='Human review permission required'), 403
    except ConflictError:
        return jsonify(error='Stale or conflicting curation operation'), 409
    except ContractError:
        return jsonify(error='Curation contract validation failed'), 422
    except Exception:
        current_app.logger.exception('Curation operation failed')
        return jsonify(error='Curation operation unavailable'), 503


@bp.post('/assertions/<assertion_id>/preview')
def preview(assertion_id):
    return _call(lambda service, reviewer: service.preview(assertion_id, reviewer=reviewer))


@bp.post('/assertions/<assertion_id>/review')
def review(assertion_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify(error='JSON object required'), 400
    return _call(lambda service, reviewer: service.review(assertion_id, body, reviewer=reviewer))
