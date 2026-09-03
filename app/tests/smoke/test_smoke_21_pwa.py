"""Smoke 21 (M15-I49): PWA readiness — manifest/service-worker infrastructure
is wired (config + icons + index.html links) and, when a production build is
present (web/dist), the precache contains zero /api entries and the SPA
navigation fallback never hijacks API paths (event-sourced data stays online)."""
import json
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[3] / "web"


@pytest.mark.smoke
def test_smoke_21_pwa_ready():
    # --- source-level infrastructure (works without node) ---
    vite_cfg = (WEB / "vite.config.ts").read_text(encoding="utf-8")
    assert "VitePWA" in vite_cfg, "vite-plugin-pwa must be configured"
    assert "navigateFallbackDenylist" in vite_cfg, "SPA fallback must not hijack /api"
    assert not re.search(r"\bruntimeCaching\s*:", vite_cfg), "API responses must never enter the SW cache"

    index_html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'rel="manifest"' in index_html
    assert "theme-color" in index_html

    assert (WEB / "public" / "pwa-192.png").exists()
    assert (WEB / "public" / "pwa-512.png").exists()

    dist = WEB / "dist"
    if not dist.exists():
        pytest.skip("web/dist not built — source-level PWA assertions passed")

    # --- build-artifact level ---
    manifest = json.loads((dist / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"
    assert any(icon.get("purpose") == "maskable" for icon in manifest["icons"])

    sw = (dist / "sw.js").read_text(encoding="utf-8")
    precache_urls = set(re.findall(r'url:"([^"]+)"', sw))
    assert precache_urls, "precache manifest must not be empty"
    assert not any("/api/" in url for url in precache_urls), "no /api route may be precached"
    assert r"/^\/api\//" in sw, "navigateFallback denylist must exclude /api"
