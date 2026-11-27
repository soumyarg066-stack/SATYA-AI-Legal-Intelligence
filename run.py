import click
from flask.cli import with_appcontext
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend import create_app
from backend.config import redact_database_uri
from backend.extensions import db
from backend.models import User
from backend.services.audit_service import record_audit_event
from backend.utils.validation import valid_email

app = create_app()


@app.cli.command("check-db")
@with_appcontext
def check_db():
    """Verify connectivity to the configured database without exposing credentials."""
    safe_uri = redact_database_uri(app.config.get("SQLALCHEMY_DATABASE_URI"))
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        db.session.rollback()
        raise click.ClickException(f"Database connection failed for {safe_uri}.") from error
    click.echo(f"Database connection succeeded ({safe_uri}).")


@app.cli.command("create-admin")
@click.option("--email", prompt=True, help="Email address for the administrator account.")
@click.option("--username", prompt=True, help="Display name for the administrator.")
@click.password_option(confirmation_prompt=True)
@with_appcontext
def create_admin(email, username, password):
    """Create or promote an administrator account without a preset password."""
    email = email.strip().lower()
    username = username.strip()
    if not valid_email(email):
        raise click.ClickException("Enter a valid email address.")
    if len(username) < 2:
        raise click.ClickException("Administrator name must contain at least 2 characters.")
    if len(password) < 10:
        raise click.ClickException("Administrator password must contain at least 10 characters.")
    try:
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(username=username, email=email, role="admin")
            db.session.add(user)
        else:
            user.username = username
            user.role = "admin"
        user.set_password(password)
        db.session.flush()
        record_audit_event(
            "admin.provision",
            user_id=user.id,
            resource_type="user",
            resource_id=user.id,
            status="success",
            details="Administrator account created or promoted via CLI.",
        )
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        raise click.ClickException(
            "Unable to save administrator account. Ensure the database is running and migrations are applied."
        ) from error
    click.echo("Administrator account is ready.")


if __name__ == "__main__":
    app.run(debug=app.config.get("DEBUG", False))
