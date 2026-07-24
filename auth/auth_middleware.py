"""
Auth middleware — validates session token, checks user exists in DB.
Must be added to middlewares list in server.py.
"""
import logging
from aiohttp import web
from sqlalchemy.orm import Session

from app.database.db import create_session
from auth.models import User


logger = logging.getLogger(__name__)
SESSION_COOKIE_NAME = "comfy_session"


def create_auth_middleware():
    @web.middleware
    async def auth_middleware(request: web.Request, handler):
        # Skip auth for public endpoints
        public_paths = {
            "/login",
            "/register",
            "/api/login",
            "/api/register",
            "/api/users",
            "/static",
            "/extensions",
        }

        if any(request.path.startswith(p) for p in public_paths):
            return await handler(request)

        # Validate session cookie
        session_token = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_token:
            return web.json_response({"error": "Unauthorized"}, status=401)

        # Validate user exists in DB
        try:
            session: Session = create_session()
            user = session.query(User).filter_by(id=session_token).first()
            if not user:
                return web.json_response({"error": "Invalid session"}, status=401)

            # Attach user to request for downstream handlers
            request["user"] = user
        except Exception as e:
            logger.error(f"Auth error: {e}")
            return web.json_response({"error": "Auth error"}, status=500)
        finally:
            if session:
                session.close()

        return await handler(request)

    return auth_middleware