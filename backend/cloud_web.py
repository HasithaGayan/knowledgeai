"""Same-origin cloud workspace. No credentials or local Ollama routes exposed."""
from pathlib import Path
from fastapi.responses import FileResponse
from backend.cloud_agents import create_agent_app

ROOT = Path(__file__).resolve().parents[1] / 'frontend'
CSP = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'"


def create_web_app(store, core, limits, origin, agents=None, conversations=None):
    app = create_agent_app(store, core, limits, origin, agents, conversations)
    def asset(name, media_type):
        return FileResponse(ROOT / name, media_type=media_type,
                            headers={'Content-Security-Policy': CSP})
    @app.get('/', include_in_schema=False)
    def home():
        return asset('cloud.html', 'text/html')
    @app.get('/assets/cloud.css', include_in_schema=False)
    def css():
        return asset('cloud.css', 'text/css')
    @app.get('/assets/cloud.js', include_in_schema=False)
    def js():
        return asset('cloud.js', 'application/javascript')
    return app
