"""PWA installation readiness: valid manifest, PNG icon endpoints and safe offline shell."""
from io import BytesIO
from fastapi.testclient import TestClient
from main import app
from PIL import Image

def test_installable_manifest_with_png_assets():
    with TestClient(app) as c:
        response=c.get("/manifest.webmanifest")
        assert response.status_code==200
        data=response.json()
        assert data["display"]=="standalone"
        assert data["scope"]=="/"
        assert data["start_url"].startswith("/")
        assert {icon["sizes"] for icon in data["icons"]}>={"192x192","512x512"}
        for size in (180,192,512):
            icon=c.get(f"/pwa-icon-{size}.png")
            assert icon.status_code==200
            assert icon.headers["content-type"].startswith("image/png")
            loaded=Image.open(BytesIO(icon.content))
            assert loaded.size==(size,size)
        assert c.get("/pwa-icon-32.png").status_code==404

def test_install_buttons_visible_without_login():
    with TestClient(app) as c:
        body=c.get("/").text
        assert 'id="installApp"' in body
        assert 'class="secondary bid-install-entry"' in body
        assert 'id="pwaInstallModal"' in body
        sw=c.get("/sw.js")
        assert sw.status_code==200
        assert "/api/" in sw.text
        assert "cache" in sw.text.lower()
