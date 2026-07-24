"""
Patched user_manager.py — overrides the original to integrate with auth_users table.
This file replaces app/user_manager.py after COPY during build.
"""
import json
import logging
import os
import re
import uuid
from typing import TYPE_CHECKING

from aiohttp import web
from sqlalchemy.orm import Session

from app.database.db import create_session
from auth.models import User


if TYPE_CHECKING:
    import folder_paths


logger = logging.getLogger(__name__)


class UserManager():
    def __init__(self):
        self.settings = None  # lazy init

    def get_users_file(self):
        user_dir = folder_paths.get_user_directory()
        return os.path.join(user_dir, "users.json")

    def get_request_user_id(self, request):
        # Auth middleware already validated and attached user to request
        if "user" in request:
            return request["user"].id

        # Fallback to comfy-user header (legacy multi-user without auth)
        user = "default"
        if "comfy-user" in request.headers:
            user = request.headers["comfy-user"]

        # Verify user exists in DB
        session: Session = create_session()
        try:
            user_record = session.query(User).filter_by(id=user).first()
            if not user_record:
                raise KeyError(f"Unknown user: {user}")
        finally:
            session.close()

        return user

    def add_user(self, username: str, password: str = None) -> str:
        """Create user with optional password (via auth routes)."""
        username = username.strip()
        if not username:
            raise ValueError("Username not provided")
        if not password:
            raise ValueError("Password not provided")

        session: Session = create_session()
        try:
            user_id = str(uuid.uuid4())
            # Hash password with bcrypt
            import bcrypt
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            user = User(
                id=user_id,
                username=username,
                password_hash=password_hash,
                is_admin=False,
            )
            session.add(user)
            session.commit()

            logger.info(f"User created: {username} ({user_id})")
            return user_id
        except Exception as e:
            session.rollback()
            raise ValueError(f"Failed to create user: {str(e)}")
        finally:
            session.close()

    def add_routes(self, routes):
        # Import auth routes and register them
        import sys
        sys.path.insert(0, '/app/ComfyUI')
        from auth.auth_routes import register_auth_routes
        register_auth_routes(routes)

        # Keep original public endpoints (read-only)
        @routes.get("/api/users")
        async def get_users(request):
            session: Session = create_session()
            try:
                users = session.query(User).all()
                return web.json_response({
                    "users": {u.id: u.username for u in users}
                })
            finally:
                session.close()