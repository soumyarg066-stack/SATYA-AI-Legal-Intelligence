from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from backend.extensions import db
from backend.models import (
    ContactMessage,
    Conversation,
    Document,
    EvidenceChunk,
    LegalSourceDocument,
    User,
)
from backend.services.audit_service import record_audit_event
from backend.services.knowledge_service import get_knowledge_status
from backend.utils.validation import clean_text, valid_email

pages_bp = Blueprint("pages", __name__)


@pages_bp.get("/")
def home():
    return render_template("index.html")


@pages_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("pages.dashboard"))
    if request.method == "POST":
        email = clean_text(request.form.get("email"), 254).lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first() if email else None
        if user and user.check_password(password):
            login_user(user, remember=bool(request.form.get("remember")))
            record_audit_event(
                "auth.login",
                user_id=user.id,
                resource_type="user",
                resource_id=user.id,
                status="success",
                commit=True,
            )
            destination = request.args.get("next", "")
            if destination.startswith("/") and not destination.startswith("//"):
                return redirect(destination)
            return redirect(url_for("pages.dashboard"))
        record_audit_event(
            "auth.login",
            user_id=user.id if user else None,
            resource_type="user",
            resource_id=user.id if user else None,
            status="failure",
            details="Invalid credentials.",
            commit=True,
        )
        flash("Email or password is incorrect.", "danger")
    return render_template("login.html")


@pages_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("pages.dashboard"))
    if request.method == "POST":
        username = clean_text(request.form.get("username"), 80)
        email = clean_text(request.form.get("email"), 254).lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        errors = []
        if len(username) < 2:
            errors.append("Username must contain at least 2 characters.")
        if not valid_email(email):
            errors.append("Enter a valid email address.")
        if len(password) < 10:
            errors.append("Password must contain at least 10 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if valid_email(email) and User.query.filter_by(email=email).first():
            errors.append("An account with that email already exists.")
        if errors:
            for message in errors:
                flash(message, "danger")
        else:
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
                login_user(user)
                return redirect(url_for("pages.dashboard"))
            except IntegrityError:
                db.session.rollback()
                flash("An account with that email already exists.", "danger")
            except SQLAlchemyError:
                db.session.rollback()
                flash("Unable to complete registration right now. Please try again.", "danger")
    return render_template("register.html")


@pages_bp.post("/logout")
@login_required
def logout():
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
    flash("You have been signed out.", "success")
    return redirect(url_for("pages.home"))


@pages_bp.get("/dashboard")
@login_required
def dashboard():
    conversations = (
        Conversation.query.filter_by(user_id=current_user.id)
        .order_by(Conversation.created_at.desc())
        .limit(5)
        .all()
    )
    return render_template(
        "dashboard.html",
        conversations=conversations,
        document_count=Document.query.count(),
        knowledge_status=get_knowledge_status(),
    )


@pages_bp.get("/chat")
@login_required
def chatbot():
    return render_template(
        "chatbot.html",
        knowledge_status=get_knowledge_status(),
    )


@pages_bp.get("/knowledge")
def knowledge_base():
    status = get_knowledge_status()
    sources = (
        LegalSourceDocument.query.filter(
            LegalSourceDocument.verification_status == "verified",
            LegalSourceDocument.chunks.any(EvidenceChunk.verification_status == "verified"),
        )
        .order_by(LegalSourceDocument.title)
        .all()
    )
    return render_template(
        "knowledge_base.html",
        knowledge_status=status,
        verified_sources=sources,
    )


@pages_bp.get("/documents")
def documents():
    return render_template("documents.html")


@pages_bp.get("/about")
def about():
    return render_template("about.html")


@pages_bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = clean_text(request.form.get("name"), 100)
        email = clean_text(request.form.get("email"), 254).lower()
        message = clean_text(request.form.get("message"), 5000)
        if len(name) < 2 or not valid_email(email) or len(message) < 10:
            flash("Please check your details and enter a message of at least 10 characters.", "danger")
        else:
            try:
                db.session.add(ContactMessage(name=name, email=email, message=message))
                db.session.commit()
                flash("Thank you. Your message has been received.", "success")
                return redirect(url_for("pages.contact"))
            except SQLAlchemyError:
                db.session.rollback()
                flash("Unable to save your message right now. Please try again.", "danger")
    return render_template("contact.html")


@pages_bp.get("/admin")
@login_required
def admin():
    if current_user.role != "admin":
        record_audit_event(
            "admin.access_denied",
            user_id=current_user.id,
            resource_type="admin_page",
            status="denied",
            commit=True,
        )
        flash("Administrator access is required.", "danger")
        return redirect(url_for("pages.dashboard"))
    return render_template("admin.html")


@pages_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        username = clean_text(request.form.get("username"), 80)
        email = clean_text(request.form.get("email"), 254).lower()
        if len(username) < 2 or not valid_email(email):
            flash("Enter a valid display name and email address.", "danger")
        else:
            existing = User.query.filter(User.email == email, User.id != current_user.id).first()
            if existing:
                flash("That email address is already in use.", "danger")
            else:
                try:
                    current_user.username = username
                    current_user.email = email
                    record_audit_event(
                        "profile.update",
                        user_id=current_user.id,
                        resource_type="user",
                        resource_id=current_user.id,
                        status="success",
                    )
                    db.session.commit()
                    flash("Your profile has been updated.", "success")
                    return redirect(url_for("pages.profile"))
                except IntegrityError:
                    db.session.rollback()
                    flash("That email address is already in use.", "danger")
                except SQLAlchemyError:
                    db.session.rollback()
                    flash("Unable to update profile right now. Please try again.", "danger")
    return render_template("profile.html")
