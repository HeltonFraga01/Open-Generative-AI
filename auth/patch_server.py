#!/usr/bin/env python3
"""Patch server.py to add auth middleware."""
import re

SERVER_PY = "/app/ComfyUI/server.py"

content = open(SERVER_PY).read()

if "# --- AUTH MIDDLEWARE INJECTION ---" in content:
    print("Already patched, skipping.")
    exit(0)

# Read the auth middleware code from the companion file
auth_code = open("/app/ComfyUI/auth/auth_inject.py").read()

# 1. Add auth_middleware to the middlewares list in __init__
# Find: middlewares = [cache_control, deprecation_warning]
# Replace with version that includes auth_middleware
content = content.replace(
    "middlewares = [cache_control, deprecation_warning]",
    "middlewares = [cache_control, deprecation_warning, auth_middleware]",
)

# 2. Find add_routes method and inject auth routes after routes = web.RouteTableDef()
# The pattern in server.py is (8-space indent):
#         routes = web.RouteTableDef()
#         self.routes = routes
content = content.replace(
    "        routes = web.RouteTableDef()\n        self.routes = routes",
    "        routes = web.RouteTableDef()\n"
    "        self.routes = routes\n"
    "        # --- AUTH ROUTES ---\n"
    "        routes.post(\"/api/auth/login\")(handle_auth_login)\n"
    "        routes.get(\"/api/auth/check\")(handle_auth_check)\n"
    "        routes.post(\"/api/auth/logout\")(handle_auth_logout)\n"
    "        routes.get(\"/auth/login\")(serve_login_page)",
)

# 3. Append the auth middleware code at the end of the file
content += "\n" + auth_code + "\n"

open(SERVER_PY, "w").write(content)
print("server.py patched successfully with auth middleware")