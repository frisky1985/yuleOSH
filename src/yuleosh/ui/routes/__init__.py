"""
yuleOSH Dashboard Server — Route subpackage.

Provides modular route handler functions extracted from the monolithic
server.py to keep individual modules focused and testable.
"""

from yuleosh.ui.routes.helpers import (
    _compute_etag,
    _format_http_datetime,
    _parse_http_datetime,
    _send_gzipped_json,
    _send_security_headers,
)

from yuleosh.ui.routes.auth_routes import (
    handle_auth_check,
    handle_auth_login,
    handle_api_action,
)

from yuleosh.ui.routes.page_routes import (
    serve_page,
    serve_file,
)

from yuleosh.ui.routes.api_routes import (
    handle_status,
    handle_health,
    list_evidence,
    list_reviews,
    list_ci_results,
    handle_pipeline_status,
    handle_usage,
)
