"""
Gatekeeper Flask Application

Main application factory and entry point.
"""

import logging
import os

from flask import Flask, jsonify, render_template, send_from_directory

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

    # Health check endpoint
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

    # Admin panel route
    @app.route('/admin')
    @app.route('/admin/')
    def admin_panel():
        """Serve the admin panel"""
        return render_template('index.html')

    return app


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

    app.register_blueprint(requests_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(approvals_bp)
    app.register_blueprint(stats_bp)


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
