"""
main/finger_control.py — Contrôle fin des doigts individuels

Fournit des helpers de haut niveau pour des positions prédéfinies
et le contrôle doigt par doigt.

Ordre des 6 doigts :
    [0] auriculaire   [1] annulaire   [2] majeur
    [3] index         [4] pouce-flex  [5] pouce-rotation

Usage :
    from main.hand_control import HandControl
    from main.finger_control import FingerControl

    hand   = HandControl('left')
    hand.connect()
    finger = FingerControl(hand)

    finger.pinch()       # pince pouce-index
    finger.point()       # doigt pointé
    finger.thumbs_up()   # pouce levé
    finger.open()        # main ouverte
"""

from main.hand_control import HandControl

# ── Index des doigts ───────────────────────────────────────────────────────
PINKY       = 0
RING        = 1
MIDDLE      = 2
INDEX       = 3
THUMB_FLEX  = 4
THUMB_ROT   = 5


class FingerControl:
    """Contrôle de haut niveau des doigts individuels."""

    def __init__(self, hand: HandControl):
        self.hand = hand

    # ── Positions prédéfinies ──────────────────────────────────────────────

    def open(self):
        """Main complètement ouverte."""
        self.hand.open()

    def close(self, value: int = 700):
        """Ferme tous les doigts à la valeur donnée."""
        self.hand.close(value)

    def pinch(self, strength: int = 600):
        """Pince pouce + index, autres doigts fermés."""
        self.hand.set_positions([
            strength,    # auriculaire
            strength,    # annulaire
            strength,    # majeur
            strength,    # index
            strength,    # pouce-flex
            0,           # pouce-rotation (ouvert)
        ])

    def point(self):
        """Doigt index pointé, autres fermés."""
        self.hand.set_positions([
            700,   # auriculaire fermé
            700,   # annulaire fermé
            700,   # majeur fermé
            0,     # index ouvert ← pointé
            500,   # pouce-flex
            0,     # pouce-rotation
        ])

    def thumbs_up(self):
        """Pouce levé, autres doigts fermés."""
        self.hand.set_positions([
            700,   # auriculaire
            700,   # annulaire
            700,   # majeur
            700,   # index
            0,     # pouce-flex ouvert ← levé
            0,     # pouce-rotation
        ])

    def peace(self):
        """Signe V / peace — index + majeur levés."""
        self.hand.set_positions([
            700,   # auriculaire
            700,   # annulaire
            0,     # majeur ouvert
            0,     # index ouvert
            500,   # pouce-flex
            0,     # pouce-rotation
        ])

    def ok_sign(self):
        """Signe OK — pouce + index pincés, autres ouverts."""
        self.hand.set_positions([
            0,     # auriculaire ouvert
            0,     # annulaire ouvert
            0,     # majeur ouvert
            600,   # index vers pouce
            600,   # pouce-flex vers index
            0,     # pouce-rotation
        ])

    # ── Contrôle individuel ────────────────────────────────────────────────

    def set_finger(self, finger_idx: int, value: int):
        """
        Modifie un seul doigt sans toucher aux autres.
        Lit la position actuelle, modifie le doigt, réécrit.

        finger_idx : 0–5 (constantes PINKY, RING, MIDDLE, INDEX, THUMB_FLEX, THUMB_ROT)
        value      : 0–1000
        """
        positions = self.hand.read_positions()
        if positions is None:
            return
        positions[finger_idx] = max(0, min(value, 1000))
        self.hand.set_positions(positions)

    def set_fingers(self, mapping: dict):
        """
        Modifie plusieurs doigts sans toucher aux autres.
        mapping : {finger_idx: value, ...}
        Ex: finger.set_fingers({INDEX: 0, MIDDLE: 0})
        """
        positions = self.hand.read_positions()
        if positions is None:
            return
        for idx, val in mapping.items():
            positions[idx] = max(0, min(int(val), 1000))
        self.hand.set_positions(positions)
