"""
scripts/spotify_setup.py — Authentification Spotify OAuth2 (one-shot, mode headless).

Prérequis :
  1. Créer une app sur https://developer.spotify.com/dashboard
  2. Ajouter exactement http://127.0.0.1:8888/callback dans les Redirect URIs de l'app
  3. Copier Client ID et Client Secret dans ~/.env :
       SPOTIFY_CLIENT_ID=...
       SPOTIFY_CLIENT_SECRET=...
  4. Lancer depuis le Jetson : python3.8 scripts/spotify_setup.py

Fonctionnement headless :
  - Le script affiche l'URL d'autorisation
  - Tu l'ouvres dans un navigateur sur ton PC
  - Après avoir accepté, Spotify redirige vers http://127.0.0.1:8888/callback?code=...
    → le navigateur affiche une erreur (normal, pas de serveur sur ton PC)
  - Tu copies l'URL complète de la barre d'adresse et tu la colles dans le terminal
  - Le script extrait le code et génère le token

Sauvegarde le token dans ~/.spotify_token.json.
"""

import json
import os
import sys
import time
import urllib.parse

import requests
from dotenv import load_dotenv

load_dotenv(os.path.expanduser('~/.env'))
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

CLIENT_ID     = os.environ.get('SPOTIFY_CLIENT_ID', '')
CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET', '')
REDIRECT_URI  = 'http://127.0.0.1:8888/callback'
TOKEN_PATH    = os.path.expanduser('~/.spotify_token.json')
SCOPES        = 'streaming user-read-currently-playing user-read-playback-state user-modify-playback-state'

if not CLIENT_ID or not CLIENT_SECRET:
    print('[SPOTIFY] ERREUR : SPOTIFY_CLIENT_ID et SPOTIFY_CLIENT_SECRET doivent être dans ~/.env')
    sys.exit(1)


def main():
    params = urllib.parse.urlencode({
        'client_id':     CLIENT_ID,
        'response_type': 'code',
        'redirect_uri':  REDIRECT_URI,
        'scope':         SCOPES,
    })
    auth_url = f'https://accounts.spotify.com/authorize?{params}'

    print('\n[SPOTIFY] ── Étape 1 ───────────────────────────────────────────────')
    print('Ouvre cette URL dans ton navigateur :')
    print(f'\n  {auth_url}\n')
    print('[SPOTIFY] ── Étape 2 ───────────────────────────────────────────────')
    print('Après avoir accepté, le navigateur affiche une erreur de connexion.')
    print('Copie l\'URL complète depuis la barre d\'adresse (elle commence par')
    print('http://127.0.0.1:8888/callback?code=...) et colle-la ici.\n')

    callback_url = input('URL de callback (ou juste le code) : ').strip()

    # Accepte l'URL complète ou juste le code
    auth_code = None
    if callback_url.startswith('http'):
        parsed = urllib.parse.urlparse(callback_url)
        params = urllib.parse.parse_qs(parsed.query)
        if 'code' in params:
            auth_code = params['code'][0]
        else:
            # Cherche code= n'importe où dans la chaîne (copier-coller imparfait)
            for part in callback_url.replace('&', '?').split('?'):
                if part.startswith('code='):
                    auth_code = part[5:]
                    break
    else:
        # L'utilisateur a collé directement le code
        auth_code = callback_url

    if not auth_code:
        print('[SPOTIFY] ERREUR : code non trouvé. Recommence depuis l\'étape 1.')
        sys.exit(1)
    print('\n[SPOTIFY] Code reçu, échange contre un token...')

    r = requests.post('https://accounts.spotify.com/api/token', data={
        'grant_type':   'authorization_code',
        'code':         auth_code,
        'redirect_uri': REDIRECT_URI,
    }, auth=(CLIENT_ID, CLIENT_SECRET), timeout=10)

    if r.status_code != 200:
        print(f'[SPOTIFY] ERREUR échange token : {r.status_code} {r.text}')
        sys.exit(1)

    token_data = r.json()
    token_data['expires_at'] = time.time() + token_data['expires_in']

    with open(TOKEN_PATH, 'w') as f:
        json.dump(token_data, f, indent=2)

    print(f'[SPOTIFY] Token sauvegardé dans {TOKEN_PATH}')
    print('[SPOTIFY] Authentification terminée. L\'agent peut maintenant contrôler Spotify.')


if __name__ == '__main__':
    main()
