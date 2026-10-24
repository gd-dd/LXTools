"""Shared LX identity; original artwork supplied by the author."""
from pathlib import Path
import sys

INK = '#202020'
ACCENT = '#507522'
BACKGROUND = '#ffffff'

def icon_path():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    return root / 'assets' / 'brand' / 'icon.png'

def readable_accent(color):
    """Keep author hue while avoiding pale headings on the light LX surface."""
    from PySide6.QtGui import QColor
    value = QColor(color)
    if not value.isValid():
        return ACCENT
    def luminance(c):
        values = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4
                  for v in (c.redF(), c.greenF(), c.blueF())]
        return sum(a*b for a,b in zip(values,(.2126,.7152,.0722)))
    surface = luminance(QColor(BACKGROUND))
    while (surface + .05) / (luminance(value) + .05) < 4.5:
        value = value.darker(110)
    return value.name()
