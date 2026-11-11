from .auth import auth_bp
from .demo import demo_bp
from .errors import error_bp
from .filters import format_datetime, hex_color, text_color
from .games import game_bp
from .health import health_bp
from .interactions import interactions_bp
from .misc import misc_bp
from .stats import stats_bp


def register_blueprints(app):
    app.register_blueprint(game_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(misc_bp)
    app.register_blueprint(error_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(demo_bp)
    app.register_blueprint(interactions_bp)


AUTOESCAPE_EXTENSIONS = (".html", ".htm", ".xml", ".xhtml", ".j2")


def select_autoescape(template_name):
    """Tell Jinja whether to HTML-escape a template's output.

    Flask only autoescapes ``.html``-like templates; questmaster templates use
    ``.j2``, so the extension is added here. Templates without a name (built
    from strings) are escaped too.

    Args:
        template_name: Name of the template being loaded, or None.

    Returns:
        True when the template output must be HTML-escaped.
    """
    if template_name is None:
        return True
    return template_name.endswith(AUTOESCAPE_EXTENSIONS)


def register_filters(app):
    app.jinja_env.autoescape = select_autoescape
    app.add_template_filter(format_datetime, name="format_datetime")
    app.jinja_env.globals.update(hex_color=hex_color, text_color=text_color)
