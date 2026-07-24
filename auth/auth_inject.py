# --- AUTH MIDDLEWARE INJECTION ---
import bcrypt
import os
import hashlib
import time
from aiohttp import web

AUTH_ENABLED = os.environ.get("COMFYUI_AUTH_ENABLED", "true").lower() == "true"
AUTH_USER = os.environ.get("COMFYUI_DEFAULT_USER", "admin")
AUTH_PASS_HASH = os.environ.get("COMFYUI_DEFAULT_PASS_HASH", "")
# Static API token for MCP/programmatic access (bypasses cookie auth)
AUTH_API_TOKEN = os.environ.get("COMFYUI_API_TOKEN", "")

LOGIN_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>ComfyUI Login</title>
<style>
body{background:#1a1a2e;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;font-family:system-ui,sans-serif}
.login-box{background:#16213e;padding:40px;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.3);width:320px}
.login-box h2{color:#e0e0e0;text-align:center;margin-bottom:24px}
.login-box input{width:100%;padding:12px;margin:8px 0;border:1px solid #334;border-radius:6px;background:#0f3460;color:#fff;box-sizing:border-box;font-size:14px}
.login-box button{width:100%;padding:12px;margin-top:16px;border:none;border-radius:6px;background:#e94560;color:#fff;font-size:16px;cursor:pointer}
.login-box button:hover{background:#c73e54}
.error{color:#e94560;text-align:center;margin-top:12px;font-size:13px}
</style>
</head><body>
<div class="login-box">
<h2>ComfyUI</h2>
<form id="loginForm">
<input type="text" id="username" placeholder="Usuario" autocomplete="username" required>
<input type="password" id="password" placeholder="Senha" autocomplete="current-password" required>
<button type="submit">Entrar</button>
<div class="error" id="err"></div>
</form>
</div>
<script>
document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const u = document.getElementById('username').value;
  const p = document.getElementById('password').value;
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: u, password: p})
    });
    if (res.ok) { window.location.reload(); }
    else { document.getElementById('err').textContent = 'Usuario ou senha invalidos'; }
  } catch(err) { document.getElementById('err').textContent = 'Erro de conexao'; }
});
</script>
</body></html>"""


def generate_session_token(username):
    raw = f"{username}:{time.time()}:{os.urandom(16).hex()}"
    return hashlib.sha256(raw.encode()).hexdigest()


_valid_sessions = {}


@web.middleware
async def auth_middleware(request, handler):
    if not AUTH_ENABLED:
        return await handler(request)

    path = request.path

    # Allow login API and login page
    if path in ("/api/auth/login", "/api/auth/check", "/api/auth/logout") or path.startswith(("/auth/", "/assets/", "/fonts/")) or path in ("/favicon.ico", "/user.css", "/materialdesignicons.min.css") or path.endswith((".js", ".css", ".woff2", ".png", ".jpg", ".ico", ".svg")):
        return await handler(request)


    # Check API token (Authorization: Bearer <token>) — for MCP/programmatic access
    if AUTH_API_TOKEN:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            if token == AUTH_API_TOKEN:
                return await handler(request)

    # Check session cookie
    session_token = request.cookies.get("comfy_session", "")
    if session_token and session_token in _valid_sessions:
        if _valid_sessions[session_token] == AUTH_USER:
            return await handler(request)

    # API and static asset requests get 401 JSON with no-cache headers to prevent CDN/Cloudflare caching
    if path not in ("/", "/index.html"):
        return web.json_response(
            {"error": "Unauthorized"},
            status=401,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
        )

    # Browser root requests get the login page with no-cache headers
    return web.Response(
        text=LOGIN_HTML,
        content_type="text/html",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}
    )


async def handle_auth_login(request):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")

    if username == AUTH_USER and AUTH_PASS_HASH:
        try:
            if bcrypt.checkpw(password.encode("utf-8"), AUTH_PASS_HASH.encode("utf-8")):
                token = generate_session_token(username)
                _valid_sessions[token] = username
                response = web.json_response({"success": True, "user": username})
                response.set_cookie("comfy_session", token, httponly=True, max_age=86400 * 7, samesite="lax")
                return response
        except Exception:
            pass

    return web.json_response({"error": "Invalid credentials"}, status=401)


async def handle_auth_check(request):
    session_token = request.cookies.get("comfy_session", "")
    if session_token and session_token in _valid_sessions:
        return web.json_response({"authenticated": True, "user": _valid_sessions[session_token]})
    return web.json_response({"authenticated": False})


async def handle_auth_logout(request):
    session_token = request.cookies.get("comfy_session", "")
    if session_token in _valid_sessions:
        del _valid_sessions[session_token]
    response = web.json_response({"success": True})
    response.del_cookie("comfy_session")
    return response


async def serve_login_page(request):
    return web.Response(text=LOGIN_HTML, content_type="text/html")

# --- END AUTH MIDDLEWARE ---