"""
scripts/calendar_setup.py — (Ré)génère le token OAuth Google Calendar.

Utilise un serveur HTTP minimal sur le port 8080 pour capturer le callback.
Prérequis : depuis ton PC, ouvrir un tunnel SSH :
    ssh -L 8080:localhost:8080 unitree@192.168.123.164
Puis ouvrir l'URL affichée dans le navigateur PC.

    python3.8 scripts/calendar_setup.py
"""

import json, os, sys, urllib.parse, urllib.request, secrets
from http.server import HTTPServer, BaseHTTPRequestHandler

TOKEN_PATH       = os.path.expanduser("~/.google_calendar_token.json")
CREDENTIALS_PATH = os.path.expanduser("~/.google_calendar_credentials.json")
REDIRECT_URI     = "http://localhost:8080"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]


def _load_client():
    """Retourne (client_id, client_secret) depuis credentials ou token existant."""
    for path in [CREDENTIALS_PATH]:
        if os.path.exists(path):
            with open(path) as f:
                d = json.load(f)
            inner = d.get("installed") or d.get("web") or d
            return inner["client_id"], inner["client_secret"]
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH) as f:
            d = json.load(f)
        cid = d.get("client_id")
        csec = d.get("client_secret")
        if cid and csec:
            print("[CALENDAR_SETUP] Credentials extraits du token existant.")
            return cid, csec
    print("[CALENDAR_SETUP] Aucun credentials trouvé.")
    print(f"  → Place le fichier OAuth Desktop app à : {CREDENTIALS_PATH}")
    sys.exit(1)


def main():
    client_id, client_secret = _load_client()

    state = secrets.token_urlsafe(16)
    auth_params = {
        "client_id":     client_id,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         " ".join(SCOPES),
        "access_type":   "offline",
        "prompt":        "consent",
        "state":         state,
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(auth_params)

    print("\n" + "="*60)
    print("PRÉREQUIS — sur ton PC, ouvre un tunnel SSH :")
    print("  ssh -L 8080:localhost:8080 unitree@192.168.123.164")
    print()
    print("Puis ouvre cette URL dans ton navigateur PC :")
    print()
    print(auth_url)
    print("="*60)
    print("En attente du callback sur port 8080...\n")

    # Serveur HTTP minimal pour capturer le code
    captured = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                captured["code"]  = params["code"][0]
                captured["state"] = params.get("state", [""])[0]
                body = b"<html><body><h2>Autorisation reussie ! Ferme cet onglet.</h2></body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Code manquant.")

        def log_message(self, *args):
            pass  # silence les logs HTTP

    server = HTTPServer(("localhost", 8080), Handler)
    server.handle_request()  # une seule requête suffit

    if "code" not in captured:
        print("[CALENDAR_SETUP] Pas de code reçu.")
        sys.exit(1)
    if captured.get("state") != state:
        print("[CALENDAR_SETUP] State invalide — possible CSRF.")
        sys.exit(1)

    # Échange du code contre les tokens
    token_data = {
        "code":          captured["code"],
        "client_id":     client_id,
        "client_secret": client_secret,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
    }
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=urllib.parse.urlencode(token_data).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        token_resp = json.loads(resp.read())

    if "error" in token_resp:
        print(f"[CALENDAR_SETUP] Erreur token : {token_resp}")
        sys.exit(1)

    # Construire le fichier token compatible google-auth
    token_json = {
        "token":         token_resp.get("access_token"),
        "refresh_token": token_resp.get("refresh_token"),
        "token_uri":     "https://oauth2.googleapis.com/token",
        "client_id":     client_id,
        "client_secret": client_secret,
        "scopes":        SCOPES,
    }
    with open(TOKEN_PATH, "w") as f:
        json.dump(token_json, f, indent=2)
    os.chmod(TOKEN_PATH, 0o600)

    print(f"[CALENDAR_SETUP] Token enregistré dans {TOKEN_PATH} ✅")
    print(f"  Scopes : {SCOPES}")


if __name__ == "__main__":
    main()
