import requests
from config import SERPER_API_KEY
from tools.registry import register


def _handler(query: str) -> str:
    try:
        r = requests.post(
            'https://google.serper.dev/search',
            headers={'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'},
            json={'q': query, 'gl': 'fr', 'hl': 'fr', 'num': 3},
            timeout=5
        )
        data = r.json()
        results = []
        if 'answerBox' in data:
            results.append(data['answerBox'].get('answer') or data['answerBox'].get('snippet', ''))
        for item in data.get('organic', [])[:3]:
            results.append(f"{item.get('title','')}: {item.get('snippet','')}")
        return '\n'.join(results) or 'Aucun résultat.'
    except Exception as e:
        return f'Erreur recherche : {e}'


register(
    schema={
        'name': 'recherche_web',
        'description': 'Recherche sur internet pour toute question générale ou d\'actualité.',
        'parameters': {
            'type': 'object',
            'properties': {'query': {'type': 'string'}},
            'required': ['query']
        }
    },
    handler=_handler
)
