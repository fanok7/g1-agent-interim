"""
Registry de tools — point central de découverte.

Chaque tool s'enregistre via register().
L'agent récupère les schémas OpenAI avec get_schemas()
et dispatche les appels avec call(name, args).

call() retourne toujours une str (les handlers peuvent retourner str ou dict) :
les tools restent indépendants du format attendu par l'API Realtime.
"""

import json

_tools = {}


def register(schema: dict, handler):
    """Enregistre un tool. schema = dict compatible OpenAI function."""
    name = schema['name']
    _tools[name] = {'schema': schema, 'handler': handler}


def get_schemas():
    return [
        {'type': 'function', **t['schema']}
        for t in _tools.values()
    ]


def call(name: str, args: dict) -> str:
    if name not in _tools:
        return f'Tool inconnu : {name}'
    try:
        result = _tools[name]['handler'](**args)
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        return f'Erreur tool {name} : {e}'


def names():
    return list(_tools.keys())
