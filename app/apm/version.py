"""Single source of the application version (M81-I243, docs/01 §BZ.1):
every version anchor — /api/health, web/package.json, the README line, git
tags — must agree with APP_VERSION here. Bumping a release means editing this
one value plus the two non-importable anchors (package.json / README), and
smoke 86 locks the trio together."""

APP_VERSION = "0.14.0"
