"""
scripts/gmail_setup.py — (Ré)génère le token OAuth Gmail.

À lancer quand l'envoi/lecture d'email échoue avec « Token has been expired or
revoked » ou « Token Gmail manquant » :

    python3.8 scripts/gmail_setup.py

Pré-requis : ~/.gmail_credentials.json (client OAuth « Desktop app » téléchargé
depuis Google Cloud Console). Écrit ~/.gmail_token.json à la fin.

Headless (Jetson sans navigateur) : le flow imprime une URL à ouvrir sur un autre
appareil. Si le navigateur ne s'ouvre pas, copie l'URL affichée, autorise le
compte g1robot.i.interim@gmail.com, et le token sera enregistré.
"""

import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

# Mêmes constantes que tools/gmail.py — ne pas diverger.
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
CREDENTIALS_PATH = os.path.expanduser('~/.gmail_credentials.json')
TOKEN_PATH = os.path.expanduser('~/.gmail_token.json')


def main() -> None:
    if not os.path.exists(CREDENTIALS_PATH):
        print(f'[GMAIL_SETUP] Fichier credentials introuvable : {CREDENTIALS_PATH}')
        print('  → Télécharge le client OAuth « Desktop app » depuis Google Cloud '
              'Console et place-le à ce chemin.')
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)

    # run_local_server ouvre le navigateur si dispo ; sinon imprime l'URL d'autorisation.
    # port=0 : port libre auto. open_browser=False pour rester utilisable en SSH.
    try:
        creds = flow.run_local_server(port=0, open_browser=False,
                                      authorization_prompt_message=
                                      'Ouvre cette URL pour autoriser le compte :\n{url}')
    except Exception as e:
        print(f'[GMAIL_SETUP] Échec run_local_server ({e}).')
        print('  → Sur un Jetson headless, relance avec un tunnel SSH '
              '(ex: ssh -L 8080:localhost:8080) ou exécute ce script sur une machine '
              'avec navigateur en copiant ~/.gmail_credentials.json.')
        sys.exit(1)

    with open(TOKEN_PATH, 'w') as f:
        f.write(creds.to_json())
    print(f'[GMAIL_SETUP] Token enregistré dans {TOKEN_PATH} ✅')


if __name__ == '__main__':
    main()
