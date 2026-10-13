"""Teemarekisteri. Komponenttien värit määritellään themes.css-tokeneissa."""

SKINS = (
    {"id": "arctic-command", "name": "Arctic Command", "description": "Yönsininen ja jäinen minttu. Rauhallinen komentokeskus."},
    {"id": "slate-electric", "name": "Slate Electric", "description": "Grafiitti, viileä sininen ja lämmin kupari."},
    {"id": "nordic-paper", "name": "Nordic Paper", "description": "Vaalea paperi ja havunvihreä. Tilaa lukemiselle."},
    {"id": "aurora-lab", "name": "Aurora Lab", "description": "Syvä indigo, laventeli ja turkoosi."},
)
DEFAULT_SKIN = "arctic-command"


def normalize_skin(value: str | None) -> str:
    return value if value in {skin["id"] for skin in SKINS} else DEFAULT_SKIN
