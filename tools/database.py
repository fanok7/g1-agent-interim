from config import SUPABASE_URL, SUPABASE_KEY
from tools.registry import register

try:
    from supabase import create_client
    _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    test = _supabase.table('formation').select('id').limit(1).execute()
    print(f'[SUPABASE] Connexion OK — {len(test.data)} ligne(s) de test')
except Exception as e:
    print(f'[SUPABASE] ERREUR connexion : {e}')
    _supabase = None


def _handler(nom: str) -> str:
    print(f'[SUPABASE] Recherche nom="{nom}"')
    if _supabase is None:
        return 'Erreur : base de données non connectée.'
    if not nom or len(nom.strip()) < 2:
        return 'Veuillez fournir un nom de famille valide.'
    try:
        result = _supabase.table('formation') \
            .select('nom, prenom, fpi, fphi, typo, certif, carte_pro, badge_date_expiration') \
            .ilike('nom', f'%{nom}%') \
            .limit(3) \
            .execute()
        if not result.data:
            return f'Aucune personne trouvée pour le nom "{nom}".'
        lignes = []
        for c in result.data:
            lignes.append(
                f"{c.get('prenom','')} {c.get('nom','')} — "
                f"Type: {c.get('typo') or 'non renseigné'} — "
                f"FPI: {c.get('fpi') or 'non planifié'} — "
                f"FPHI: {c.get('fphi') or 'non planifié'} — "
                f"Certif: {c.get('certif') or 'non planifié'} — "
                f"Badge expire: {c.get('badge_date_expiration') or 'aucun'}"
            )
        return '\n'.join(lignes)
    except Exception as e:
        print(f'[SUPABASE] ERREUR : {e}')
        return f'Erreur base de données : {e}'


register(
    schema={
        'name': 'chercher_formation',
        'description': 'Recherche les infos de formation d\'une personne par son nom de famille.',
        'parameters': {
            'type': 'object',
            'properties': {'nom': {'type': 'string'}},
            'required': ['nom']
        }
    },
    handler=_handler
)
