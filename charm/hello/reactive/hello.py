import os
import subprocess

from charmhelpers.core import hookenv, templating
from charms.reactive import endpoint_from_flag, when, when_not, set_flag


def clone_app_repo(repo_url, destination):
    """Clone the repository from the given URL to the given destination."""
    if not os.path.isdir(destination):
        hookenv.log(f"Cloning {repo_url} to {destination}")
        subprocess.check_call(["git", "clone", repo_url, destination])
    else:
        hookenv.log(f"Skipping the cloning as {destination} exists already")


def create_virtualenv(path):
    """Create a virtualenv environment at the given path."""
    if not os.path.isdir(path):
        hookenv.log(f"Creating a new virtualenv environment at {path}")
        subprocess.check_call(["virtualenv", path])
    else:
        hookenv.log(
            "Skipping the creation of the virtualenv environment"
            " as it exists already"
        )


def install_requirements(virtualenv_dir, app_dir):
    """Install the requirements of the given app."""
    hookenv.log("Installing the requirements for the hello app")
    subprocess.check_call(
        [
            f"{virtualenv_dir}/bin/pip",
            "install",
            "-r",
            f"{app_dir}/requirements.txt"
        ]
    )


def setup_database_credentials(app_dir, db):
    """Render the database credentials to the django settings file."""

    db_credentials = dict(
        db_host=db.master.host,
        db_port=db.master.port,
        db_name=db.master.dbname,
        db_user=db.master.user,
        db_password=db.master.password,
    )
    settings_file = f"{app_dir}/hello/hello/settings_local.py"
    hookenv.log(f"Rendering database credentials to {settings_file}")
    templating.render("settings_local.py.tmpl", settings_file, db_credentials)


def run_migrations(venv_dir, app_dir):
    """Run the Django migrations for the given app."""
    hookenv.log("Running the migrations")
    subprocess.check_call(
        [f"{venv_dir}/bin/python3", "manage.py", "migrate"],
        cwd=f"{app_dir}/hello"
    )


@when("db.master.available")
@when_not("database.configured")
def setup_database():
    """Set up the database for the hello app."""
    config = hookenv.config()
    hookenv.status_set("maintenance", "Setting up the database")
    app_dir = config["app-dir"]
    venv_dir = config["app-venv-dir"]
    db = endpoint_from_flag("db.master.available")
    setup_database_credentials(app_dir, db)
    run_migrations(venv_dir, app_dir)
    set_flag("database.configured")


@when_not("db.master.available")
@when("hello.installed")
def waiting_for_database():
    """Set the status when a PostgreSQL database is not available."""
    hookenv.log("Blocked waiting for a PostgreSQL database")
    hookenv.status_set("blocked", "A PostgreSQL database is required")


@when_not("hello.installed")
def install_hello():
    """Install the hello app."""
    config = hookenv.config()
    app_dir = config["app-dir"]
    venv_dir = config["app-venv-dir"]
    clone_app_repo(config["app-repo-url"], app_dir)
    create_virtualenv(venv_dir)
    install_requirements(venv_dir, app_dir)
    hookenv.log("Finished installing the hello application")
    set_flag("hello.installed")


@when("hello.installed", "database.configured")
@when_not("gunicorn.configured")
def setup_gunicorn():
    hookenv.log("Setting up gunicorn")
    config = hookenv.config()
    venv_dir = config["app-venv-dir"]
    app_dir = config["app-dir"]
    subprocess.check_call([f"{venv_dir}/bin/pip", "install", "gunicorn"])
    templating.render(
        "gunicorn.service.tmpl",
        "/etc/systemd/system/gunicorn.service",
        dict(app_dir=app_dir, venv_dir=venv_dir)
    )
    subprocess.check_call(["systemctl", "daemon-reload"])
    subprocess.check_call(["systemctl", "enable", "gunicorn.service"])
    subprocess.check_call(["systemctl", "start", "gunicorn.service"])
    hookenv.open_port(8000)
    hookenv.status_set("active", "The app is running.")
    set_flag("gunicorn.configured")
