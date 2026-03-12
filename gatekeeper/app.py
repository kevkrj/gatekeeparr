"""
Gatekeeper Flask Application

Main application factory and entry point.
"""

import logging
import os

from flask import Flask, jsonify, redirect, render_template, request, session, url_for

from gatekeeper.config import get_config, Config
from gatekeeper.models import init_db


def create_app(config: Config = None) -> Flask:
    """
    Create and configure the Flask application.

    Args:
        config: Optional configuration object. If None, loads from environment.

    Returns:
        Configured Flask application
    """
    # Get the admin template/static directories
    admin_dir = os.path.join(os.path.dirname(__file__), 'admin')

    app = Flask(
        __name__,
        template_folder=os.path.join(admin_dir, 'templates'),
        static_folder=os.path.join(admin_dir, 'static')
    )

    # Load configuration
    if config is None:
        config = get_config()

    # Flask configuration
    app.config['SECRET_KEY'] = config.secret_key
    app.config['SQLALCHEMY_DATABASE_URI'] = config.database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Initialize database
    init_db(app)

    # Register blueprints
    _register_blueprints(app)

    # Register error handlers
    _register_error_handlers(app)

    # Register auth routes and API protection
    _register_auth(app)

    # Health check endpoint (unauthenticated)
    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({'status': 'healthy', 'version': '0.1.0'}), 200

    # Test endpoint
    @app.route('/test', methods=['GET'])
    def test():
        """Test endpoint to verify AI integration"""
        from gatekeeper.services.analyzer import get_analyzer
        try:
            analyzer = get_analyzer()
            result = analyzer.analyze(
                "The Dark Knight",
                "When the menace known as the Joker wreaks havoc on Gotham, Batman must face his greatest challenge.",
                2008
            )
            return jsonify({
                'status': 'ok',
                'provider': result.provider,
                'model': result.model,
                'result': result.to_dict()
            }), 200
        except Exception as e:
            return jsonify({'status': 'error', 'error': str(e)}), 500

    # Connection test endpoints
    @app.route('/test/connections', methods=['GET'])
    def test_connections():
        """Test connections to all external services"""
        from gatekeeper.services.jellyseerr import JellyseerrClient
        from gatekeeper.services.radarr import RadarrClient
        from gatekeeper.services.sonarr import SonarrClient

        results = {}

        try:
            jellyseerr = JellyseerrClient()
            results['jellyseerr'] = jellyseerr.test_connection()
        except Exception as e:
            results['jellyseerr'] = False
            results['jellyseerr_error'] = str(e)

        try:
            radarr = RadarrClient()
            results['radarr'] = radarr.test_connection()
        except Exception as e:
            results['radarr'] = False
            results['radarr_error'] = str(e)

        try:
            sonarr = SonarrClient()
            results['sonarr'] = sonarr.test_connection()
        except Exception as e:
            results['sonarr'] = False
            results['sonarr_error'] = str(e)

        all_ok = all(results.get(k) for k in ['jellyseerr', 'radarr', 'sonarr'])
        return jsonify({
            'status': 'ok' if all_ok else 'partial',
            'connections': results
        }), 200 if all_ok else 207

    # Setup wizard route
    @app.route('/setup')
    @app.route('/setup/')
    def setup_wizard():
        """Serve the setup wizard page"""
        return render_template('setup.html')

    # Admin panel route (authenticated)
    @app.route('/admin')
    @app.route('/admin/')
    def admin_panel():
        """Serve the admin panel"""
        if not session.get('user'):
            return redirect(url_for('login'))
        return render_template('index.html')

    return app


def _register_auth(app: Flask):
    """Register authentication routes and API before_request hook."""
    from gatekeeper.auth import login_via_jellyseerr

    @app.route('/login', methods=['GET'])
    def login():
        """Show the login page."""
        # Already logged in? Go to admin.
        if session.get('user'):
            return redirect(url_for('admin_panel'))
        return render_template('login.html')

    @app.route('/login', methods=['POST'])
    def login_post():
        """Handle login form submission (JSON)."""
        data = request.get_json(silent=True) or {}
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required.'}), 400

        user_data = login_via_jellyseerr(email, password)
        if user_data is None:
            return jsonify({'success': False, 'error': 'Invalid credentials. Please try again.'}), 401

        # Store essential user info in session
        session.permanent = True
        session['user'] = {
            'id': user_data.get('id'),
            'email': user_data.get('email', ''),
            'username': user_data.get('username', ''),
            'display_name': user_data.get('displayName', ''),
            'avatar': user_data.get('avatar', ''),
            'permissions': user_data.get('permissions', 0),
            'user_type': user_data.get('userType', 0),
            'is_admin': bool(user_data.get('permissions', 0) & 2),
        }

        return jsonify({'success': True, 'redirect': '/admin'}), 200

    @app.route('/logout', methods=['GET'])
    def logout():
        """Clear the session and redirect to login."""
        session.clear()
        return redirect(url_for('login'))

    @app.route('/api/auth/me', methods=['GET'])
    def auth_me():
        """Return current session user info (for the frontend)."""
        user = session.get('user')
        if not user:
            return jsonify({'authenticated': False}), 401
        return jsonify({'authenticated': True, 'user': user}), 200

    # Protect all /api/* routes (except auth and setup endpoints)
    @app.before_request
    def protect_api():
        """Require authentication for API endpoints. Redirect to setup wizard if needed."""
        path = request.path

        # Always allow setup-related paths
        if path.startswith('/setup') or path.startswith('/api/setup/'):
            return None

        # Webhooks and action callbacks: optionally authenticated via shared secret
        if path.startswith('/webhook/') or path.startswith('/webhook') or path.startswith('/action'):
            webhook_secret = get_config().webhook_secret
            if webhook_secret:
                provided = request.headers.get('X-Webhook-Secret', '')
                if provided != webhook_secret:
                    return jsonify({'error': 'Invalid webhook secret'}), 403
            return None
        if path in ('/health', '/login', '/logout', '/api/auth/me'):
            return None
        if path.startswith('/static/'):
            return None
        if path.startswith('/test'):
            return None
        if path.startswith('/maintenance/'):
            return None

        # Check if first-run setup is needed (no users in DB)
        # Redirect browser navigation to /setup during first run
        if path in ('/', '/admin', '/admin/', '/login'):
            from gatekeeper.api.setup import setup_needed
            try:
                if setup_needed():
                    return redirect('/setup')
            except Exception:
                pass

        # Protect /api/* endpoints
        if path.startswith('/api/'):
            user = session.get('user')
            if not user:
                return jsonify({'error': 'Authentication required'}), 401

        return None


def _register_blueprints(app: Flask):
    """Register all blueprints"""
    from gatekeeper.webhooks.jellyseerr import jellyseerr_bp
    from gatekeeper.webhooks.actions import actions_bp
    from gatekeeper.webhooks.radarr import radarr_bp
    from gatekeeper.webhooks.sonarr import sonarr_bp

    app.register_blueprint(jellyseerr_bp)
    app.register_blueprint(actions_bp)
    app.register_blueprint(radarr_bp)
    app.register_blueprint(sonarr_bp)

    # API blueprints
    from gatekeeper.api.requests import requests_bp
    from gatekeeper.api.users import users_bp
    from gatekeeper.api.approvals import approvals_bp
    from gatekeeper.api.stats import stats_bp
    from gatekeeper.api.setup import setup_bp

    app.register_blueprint(requests_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(approvals_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(setup_bp)


def _register_error_handlers(app: Flask):
    """Register error handlers"""

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        return jsonify({'error': 'Internal server error'}), 500


def run():
    """Run the application"""
    config = get_config()
    app = create_app(config)
    app.run(
        host=config.host,
        port=config.port,
        debug=config.debug
    )


if __name__ == '__main__':
    run()
