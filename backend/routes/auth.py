from flask import Blueprint, jsonify
from flask_login import current_user, login_user, logout_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.extensions import db
from backend.models import User
from backend.services.audit_service import record_audit_event
from backend.utils.validation import clean_text, json_object, valid_email

auth_bp = Blueprint("auth_api", __name__)


@auth_bp.post("/register")
def register():
    data = json_object()
    if data is None:
        return jsonify(error="A JSON object is required."), 400
    username = clean_text(data.get("username"), 80)
    email = clean_text(data.get("email"), 254).lower()
    password = data.get("password", "")

    if len(username) < 2:
        return jsonify(error="Username must contain at least 2 characters."), 400
    if not valid_email(email):
        return jsonify(error="Enter a valid email address."), 400
    if not isinstance(password, str) or len(password) < 10:
        return jsonify(error="Password must contain at least 10 characters."), 400
    if User.query.filter_by(email=email).first():
        record_audit_event(
            "auth.register",
            resource_type="user",
            status="failure",
            details="Duplicate email registration attempt.",
            commit=True,
        )
        return jsonify(error="An account with that email already exists."), 409

    user = User(username=username, email=email, role="user")
    user.set_password(password)
    try:
        db.session.add(user)
        db.session.flush()
        record_audit_event(
            "auth.register",
            user_id=user.id,
            resource_type="user",
            resource_id=user.id,
            status="success",
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="An account with that email already exists."), 409
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error="Unable to create account due to a database error."), 500

    login_user(user)
    return jsonify(user=user.to_dict()), 201


@auth_bp.post("/login")
def login():
    data = json_object()
    if data is None:
        return jsonify(error="A JSON object is required."), 400
    email = clean_text(data.get("email"), 254).lower()
    password = data.get("password", "")
    if not email or not isinstance(password, str):
        return jsonify(error="Email or password is incorrect."), 401

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        record_audit_event(
            "auth.login",
            user_id=user.id if user else None,
            resource_type="user",
            resource_id=user.id if user else None,
            status="failure",
            details="Invalid credentials.",
            commit=True,
        )
        return jsonify(error="Email or password is incorrect."), 401

    login_user(user, remember=bool(data.get("remember", False)))
    record_audit_event(
        "auth.login",
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        status="success",
        commit=True,
    )
    return jsonify(user=user.to_dict())


@auth_bp.post("/logout")
def logout():
    if current_user.is_authenticated:
        user_id = current_user.id
        logout_user()
        record_audit_event(
            "auth.logout",
            user_id=user_id,
            resource_type="user",
            resource_id=user_id,
            status="success",
            commit=True,
        )
    return jsonify(message="You have been signed out.")


@auth_bp.get("/me")
def me():
    if not current_user.is_authenticated:
        return jsonify(error="Authentication required."), 401
    return jsonify(user=current_user.to_dict())
