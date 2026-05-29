from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.routing import APIRoute

# 1. App Metadata (With Native Unicode Emojis)
TITLE = "Task Management API"
VERSION = "1.0.0"
DESCRIPTION = """
Backend API for a Task Management System with Role-Based Access Control (RBAC). Built using FastAPI and SQLAlchemy, this API provides endpoints for user authentication, task management and role administration. The system supports three primary roles: Admin, Manager, and User - each with distinct permissions to ensure secure and efficient task handling.

### RBAC Overview

**Admin**: Unrestricted global data visibility, deletion, and user routing.

**Manager**: Mid-tier access. Can create, view, and assign tasks within their scope.

**User**: View and update the progress status of tasks assigned to *them only*.

"""

# 2. Tag Group Organization
TAGS_METADATA = [
    {
        "name": "Authentication",
        "description": "Supports JWT authentication, token refreshing and session validation.",
    },
    {
        "name": "Tasks",
        "description": "Endpoints for creating, viewing, updating, and deleting tasks. Access is role-based.",
    },
    {
        "name": "Roles",
        "description": "Endpoints for managing system roles and permissions.",
    },
]

# 3. Advanced Behavior Parameters
SWAGGER_PARAMETERS = {
    "docExpansion": "list",  # Keeps tags open by default
    "operationsSorter": "alpha",  # Sorts endpoints alphabetically
    "tagsSorter": "alpha",  # Sorts tags/groups alphabetically
    "displayRequestDuration": True,  # Shows execution time in milliseconds
    "defaultModelsExpandDepth": -1,  # Hides the bottom 'Schemas' section completely
}


def configure_swagger(app: FastAPI) -> None:
    """
    Applies custom UI setups, clean operation IDs, and routes to the FastAPI app.
    Uses unified CDN assets to prevent layout breakdown.
    """

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui_html():
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{app.title} - Documentation",
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
            # Matched core assets from the exact same bundle to prevent breaking
            swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
            swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
            swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
            swagger_ui_parameters=SWAGGER_PARAMETERS,
        )

    # 4. Clean Operation IDs (Run last to capture all routes)
    for route in app.routes:
        if isinstance(route, APIRoute):
            route.operation_id = route.name
