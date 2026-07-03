# Module main/ — Contrôle des mains Inspire RH56E2

## Structure

```
main/
├── __init__.py          # exports principaux
├── hand_control.py      # bas niveau Modbus (connexion, capteurs, doigts)
├── shake_hand.py        # logique poignée de main (SDK + Modbus + capteur)
└── finger_control.py    # positions prédéfinies et contrôle doigt par doigt

tools/
└── shake_hand_tool.py   # tool GPT → appelle main.shake_hand

agent/
└── shake_hand_loop.py   # boucle async → notifie GPT des événements
```

## Déploiement

```bash
# Copier le dossier main/
cp -r main/ /home/unitree/g1_agent_interim/main/

# Copier les tools
cp tools/shake_hand_tool.py /home/unitree/g1_agent_interim/tools/

# Copier la boucle agent (si pas déjà fait)
cp agent/shake_hand_loop.py /home/unitree/g1_agent_interim/agent/
```

## Patch main.py (3 lignes)

```python
# 1. Dans le bloc imports tools :
import tools.shake_hand_tool  # noqa: F401

# 2. Dans le bloc imports agent :
from agent.shake_hand_loop import shake_hand_event_loop

# 3. Dans asyncio.gather() :
shake_hand_event_loop(ws),
```

## Patch robot/gestures.py

Retirer 'serrer_main' de ACTION_MAP (maintenant géré par shake_hand_tool) :

```python
ACTION_MAP = {
    'saluer':            25,
    # 'serrer_main':     27,  ← RETIRER
    'tope_la':           18,
    ...
}
```

## Test standalone

```bash
# Test poignée de main seule
python3.8 -c "
import sys; sys.path.insert(0, '/home/unitree/g1_agent_interim')
import robot.hardware as hw; hw.init()
from main.shake_hand import run_shake_hand
run_shake_hand('left')
"

# Test contrôle bas niveau
python3.8 -c "
import sys; sys.path.insert(0, '/home/unitree/g1_agent_interim')
from main.hand_control import HandControl
hand = HandControl('left')
hand.connect()
hand.set_speed(300)
hand.close(500)
import time; time.sleep(2)
hand.open()
hand.disconnect()
"
```

## Flux complet quand on dit "serre-moi la main"

```
"serre-moi la main"
        ↓
GPT → serrer_main()          [tools/shake_hand_tool.py]
        ↓
thread → run_shake_hand()    [main/shake_hand.py]
        ↓
ExecuteAction(27)            → bras lève
        ↓
capteur paume surveille...   [main/hand_control.py]
        ↓
main détectée → event 'handshake_start' → GPT dit quelque chose
        ↓
doigts ferment progressivement (Modbus)
        ↓
main retirée → event 'handshake_end' → GPT dit au revoir
        ↓
doigts ouvrent + ExecuteAction(99)   → bras baisse
```
