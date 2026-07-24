"""
Auth routes — /api/login, /api/register, /api/logout.
These are added to the server's routes via PromptServer.add_routes().
"""
import uuid
from datetime import datetime
from aiohttp import web
from sqlalchemy.orm import Session

from app.database.db import create_session
from auth.models import User


def register_auth_routes(routes):
    @routes.post("/api/register")
    async def register(request: web.Request):
        body = await request.json()
        username = body.get("username", "").strip()
        password = body.get("password", "")

        if not username or not password:
            return web.json_response({"error": "Username and password required"}, status=400)

        session: Session = create_session()
        try:
            # Check existing user
            existing = session.query(User).filter_by(username=username).first()
            if existing:
                return web.json_response({"error": "Username already exists"}, status=400)

            # Create user (hash in user_manager, not here)
            user_id = str(uuid.uuid4())
            user = User(
                id=user_id,
                username=username,
                password_hash="",  # set later by UserManager.add_user
                is_admin=False,
                created_at=datetime.utcnow(),
            )
            session.add(user)
            session.commit()

            return web.json_response({"user_id": user_id, "username": username})
        except Exception as e:
            session.rollback()
            return web.json_response({"error": f"Registration failed: {str(e)}"}, status=500)
        finally:
            session.close()

    @routes.post("/api/login")
    async def login(request: web.Request):
        body = await request.json()
        username = body.get("username", "").strip()
        password = body.get("password", "")

        if not username or not password:
            return web.json_response({"error": "Username and password required"}, status=400)

        session: Session = create_session()
        try:
            user = session.query(User).filter_by(username=username).first()
            if not user:
                return web.json_response({"error": "Invalid credentials"}, status=401)

            # Verify password with bcrypt
            import bcrypt
            if not bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
                return web.json_response({"error": "Invalid credentials"}, status=401)

            # Update last login
            user.last_login = datetime.utcnow()
            session.commit()

            # Set session cookie (token = user_id for simplicity; use proper JWT in production)
            response = web.json_response({"user_id": user.id, "username": user.username, "is_admin": user.is_admin})
            response.set_cookie("comfy_session", user.id, httponly=True, max_age=86400 * 7)  # 7 days
            return response
        except Exception as e:
            return web.json_response({"error": f"Login failed: {str(e)}"}, status=500)
        finally:
            session.close()

    @routes.post("/api/logout")
    async def logout(request: web.Request):
        response = web.json_response({"success": True})
        response.del_cookie("comfy_session")
        return response