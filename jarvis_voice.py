"""jarvis_voice.py - Registro central de voz MASCULINA para JARVIS y ULTRON.

Antes, la voz estaba repartida por media docena de ficheros y el respaldo por
defecto de ElevenLabs era `21m00Tcm4TlvDq8ikWAM` (Rachel), que es una voz
*femenina*: sin `ELEVENLABS_VOICE_ID` en el entorno, Jarvis hablaba en femenino.
Este modulo concentra la decision en un solo sitio y garantiza que ambos
agentes suenen siempre masculinos, con timbres distintos entre si:

    JARVIS  - baritono britanico sereno, ritmo de mayordomo.
    ULTRON  - baritono mas grave, mas lento, con pausas largas.

Cada capa de sintesis tiene su propio ajuste dentro del mismo perfil:

    ElevenLabs  -> voice_id + voice_settings
    Piper       -> modelo .onnx local (offline, gratis)
    Windows SAPI-> preferencia de voz + velocidad
    Navegador   -> lo consume hud_assets/voice.js (mismos rate/pitch)

Uso:
    from jarvis_voice import perfil, voz_elevenlabs, voz_piper
    p = perfil("ultron")
    p.rate, p.pitch, p.piper_voice, p.elevenlabs_voice
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List

__all__ = [
    "VoiceProfile", "PERFILES", "perfil", "voz_elevenlabs", "voz_piper",
    "ajustes_elevenlabs", "es_voz_femenina", "VOCES_ELEVENLABS_MASCULINAS",
]


# ── Voces masculinas de ElevenLabs (IDs oficiales del catalogo por defecto) ──
# Solo voces masculinas: esta tabla es la que impide que el respaldo caiga en
# una voz femenina cuando el usuario no configura nada.
VOCES_ELEVENLABS_MASCULINAS: Dict[str, str] = {
    "daniel":  "onwK4e9ZLuTAKqWW03F9",  # britanico, autoritario, locutor
    "george":  "JBFqnCBsd6RMkjVDRZzb",  # britanico, calido, narracion
    "callum":  "N2lVS1w4EtoT3dr4eOWO",  # transatlantico, intenso
    "adam":    "pNInz6obpgDQGcFmaJgB",  # americano, profundo
    "brian":   "nPczCjzI2devNBz1zQrb",  # americano, grave
    "clyde":   "2EiwWnXFnvU5JabPnv8n",  # aspero, veterano
    "liam":    "TX3LPaxmHKxFdv7VOQHJ",  # americano, joven
    "antoni":  "ErXwobaYiN019PkySvjV",  # americano, sereno
    "arnold":  "VR6AewLTigWG4xSOukaG",  # americano, nitido
    "spuds":   "NOpBlnGInO9m6vDvFkFC",  # Spuds Oxley (el de .env.example)
}

# Voces femeninas conocidas: si alguna aparece configurada, avisamos.
VOCES_ELEVENLABS_FEMENINAS: Dict[str, str] = {
    "rachel":    "21m00Tcm4TlvDq8ikWAM",
    "domi":      "AZnzlk1XvdvUeBnXmlld",
    "bella":     "EXAVITQu4vr4xnSDxMaL",
    "elli":      "MF3mGyEYCl7XYWbV9V6O",
    "charlotte": "XB0fDUnXU5powFXDhCwa",
    "matilda":   "XrExE9yKIg1WjnnlVkGX",
    "lily":      "pFZP5JQG7iQjIQuC4Bku",
    "dorothy":   "ThT5KcBeYPX3keUQqHPh",
    "nicole":    "piTKgcLEGmPE4e6mEKli",
    "freya":     "jsCqWAovK2LkecY7zXl4",
}

# ── Voces Piper en espanol (offline). Todas las del catalogo rhasspy en
# espanol son masculinas salvo es_AR-daniela-high, que queda excluida. ──
VOCES_PIPER_MASCULINAS: List[str] = [
    "es_MX-claude-high",       # mejor calidad, espanol neutro latino
    "es_ES-sharvard-medium",   # castellano, timbre mas grave
    "es_ES-davefx-medium",     # castellano, equilibrado
    "es_MX-ald-medium",        # latino, calido
    "es_ES-carlfm-x_low",      # el mas rapido, calidad justa
]


@dataclass
class VoiceProfile:
    """Un timbre completo para un agente, en todas las capas de sintesis."""

    agente: str
    elevenlabs_voice: str          # ID de ElevenLabs (siempre masculina)
    piper_voice: str               # modelo Piper local
    piper_fallbacks: List[str]     # si el modelo preferido no descarga
    rate: float                    # velocidad (1.0 = natural)
    pitch: float                   # gravedad para el navegador (menor = mas grave)
    sapi_rate: int                 # velocidad SAPI de Windows (-10..10)
    stability: float               # ElevenLabs: constancia del timbre
    similarity: float              # ElevenLabs: fidelidad a la voz original
    style: float = 0.0             # ElevenLabs: intensidad interpretativa
    cadencia: float = 1.0          # multiplicador de pausas entre frases
    descripcion: str = ""
    sapi_prefer: List[str] = field(default_factory=list)


PERFILES: Dict[str, VoiceProfile] = {
    # ── JARVIS: mayordomo. Grave pero calido; nunca dramatico. ──────────────
    "jarvis": VoiceProfile(
        agente="JARVIS",
        elevenlabs_voice=VOCES_ELEVENLABS_MASCULINAS["daniel"],
        piper_voice="es_ES-davefx-medium",
        piper_fallbacks=["es_MX-claude-high", "es_ES-sharvard-medium", "es_ES-carlfm-x_low"],
        rate=0.99,
        pitch=0.80,
        sapi_rate=0,
        stability=0.55,
        similarity=0.80,
        style=0.10,
        cadencia=1.0,
        descripcion="Baritono britanico sereno. Pausado, cortes, sin dramatismo.",
        sapi_prefer=["alvaro", "pablo", "jorge", "enrique", "diego"],
    ),
    # ── ULTRON: mas grave, mas lento, con silencios que pesan. ──────────────
    "ultron": VoiceProfile(
        agente="ULTRON",
        elevenlabs_voice=VOCES_ELEVENLABS_MASCULINAS["callum"],
        piper_voice="es_ES-sharvard-medium",
        piper_fallbacks=["es_MX-claude-high", "es_ES-davefx-medium", "es_ES-carlfm-x_low"],
        rate=0.86,
        pitch=0.58,
        sapi_rate=-2,
        stability=0.32,      # menos estable = mas expresivo, mas amenazante
        similarity=0.88,
        style=0.45,
        cadencia=1.35,
        descripcion="Baritono metalico. Lento, con pausas largas y filo.",
        sapi_prefer=["jorge", "raul", "alvaro", "pablo", "enrique"],
    ),
}


def _clave(agente: str | None) -> str:
    a = (agente or "").strip().lower()
    if a in PERFILES:
        return a
    # ULTRON_MODE=1 lo activa ultron_core al arrancar
    if os.getenv("ULTRON_MODE", "").strip() in ("1", "true", "True"):
        return "ultron"
    return "jarvis"


def perfil(agente: str | None = None) -> VoiceProfile:
    """Perfil de voz del agente. Sin argumento, deduce cual esta activo."""
    return PERFILES[_clave(agente)]


def es_voz_femenina(voice_id: str) -> bool:
    """True si el ID corresponde a una voz femenina conocida de ElevenLabs."""
    v = (voice_id or "").strip()
    return v in VOCES_ELEVENLABS_FEMENINAS.values()


def voz_elevenlabs(agente: str | None = None, log=None) -> str:
    """ID de voz de ElevenLabs para el agente.

    Prioridad: variable de entorno especifica del agente > variable global >
    perfil masculino por defecto. Si lo configurado es una voz femenina
    conocida, se respeta la decision del usuario pero se deja constancia:
    puede ser intencionado, y no nos corresponde revocarlo en silencio.
    """
    p = perfil(agente)
    clave = _clave(agente)

    candidatos = []
    if clave == "ultron":
        candidatos.append(os.getenv("ULTRON_VOICE_ID", "").strip())
    else:
        candidatos.append(os.getenv("JARVIS_VOICE_ID", "").strip())
    candidatos.append(os.getenv("ELEVENLABS_VOICE_ID", "").strip())

    for v in candidatos:
        if not v or "tu_" in v.lower():
            continue
        if es_voz_femenina(v) and log:
            log(f"[VOZ] {p.agente}: el ID {v} es una voz femenina de ElevenLabs. "
                f"Deja la variable vacia para usar la masculina por defecto.")
        return v

    return p.elevenlabs_voice


def ajustes_elevenlabs(agente: str | None = None) -> dict:
    """Bloque `voice_settings` de la peticion a ElevenLabs para este agente."""
    p = perfil(agente)
    return {
        "stability": p.stability,
        "similarity_boost": p.similarity,
        "style": p.style,
        "use_speaker_boost": True,
    }


def voz_piper(agente: str | None = None) -> str:
    """Modelo Piper preferido para el agente (respetando PIPER_VOICE si existe)."""
    forzada = os.getenv("PIPER_VOICE", "").strip()
    if forzada:
        return forzada
    return perfil(agente).piper_voice


def cadena_piper(agente: str | None = None) -> List[str]:
    """Modelo preferido seguido de sus respaldos, sin repetir."""
    p = perfil(agente)
    out, vistos = [], set()
    for v in [voz_piper(agente)] + p.piper_fallbacks:
        if v and v not in vistos:
            vistos.add(v)
            out.append(v)
    return out


def resumen(agente: str | None = None) -> dict:
    """Snapshot legible del perfil, para el endpoint /voice_status y el HUD."""
    p = perfil(agente)
    return {
        "agente": p.agente,
        "genero": "masculino",
        "descripcion": p.descripcion,
        "elevenlabs_voice": voz_elevenlabs(agente),
        "piper_voice": voz_piper(agente),
        "piper_cadena": cadena_piper(agente),
        "rate": p.rate,
        "pitch": p.pitch,
        "sapi_rate": p.sapi_rate,
        "cadencia": p.cadencia,
    }


if __name__ == "__main__":  # pragma: no cover - inspeccion manual
    import json
    for a in ("jarvis", "ultron"):
        print(json.dumps(resumen(a), indent=2, ensure_ascii=False))
