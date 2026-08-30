#!/usr/bin/env python3
"""
jarvis_redact.py - Redacción de secretos antes de guardar en disco.
Adaptado de isair/jarvis (utils/redact.py): emails, tarjetas, claves de
API, JWT, OTP y cabeceras de autorización se enmascaran para que una
mención accidental en una conversación no acabe en la base de memoria,
avisos, diario ni logs.
"""
import re

_REDACTION_RULES: list = [
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", re.IGNORECASE), "[REDACTED_EMAIL]"),
    (re.compile(r"\b(?:\d[ -]*?){13,19}\b"), "[REDACTED_CARD]"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"), "[REDACTED_STRIPE_KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "[REDACTED_GH_TOKEN]"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "[REDACTED_GOOG_KEY]"),
    (re.compile(r"Authorization:\s*Bearer\s+\S+", re.IGNORECASE), "Authorization: Bearer [REDACTED]"),
    (re.compile(r"Authorization:\s*Basic\s+[A-Za-z0-9+/=]+", re.IGNORECASE), "Authorization: Basic [REDACTED]"),
    (re.compile(r"\b(AWS|GH|GCP|AZURE|xox[abpcr]-)[A-Za-z0-9_\-]{10,}\b", re.IGNORECASE), "[REDACTED_TOKEN]"),
    (re.compile(r"\b(?:eyJ[0-9A-Za-z._\-]+)\b"), "[REDACTED_JWT]"),
    (re.compile(
        r"\b(pass(?:word)?|secret|token|apikey|api_key|"
        r"(?:refresh|access|id|oauth)_?token|session(?:_?id)?|sid)"
        r"\s*[:=]\s*\S+\b",
        re.IGNORECASE,
    ), r"\1=[REDACTED]"),
    (re.compile(r"\b[0-9A-Fa-f]{32,}\b"), "[REDACTED_HEX]"),
    (re.compile(r"\b\d{6}\b(?=.*(otp|2fa|code))", re.IGNORECASE), "[REDACTED_OTP]"),
]


def redact(text: str, max_len: int = 8000) -> str:
    """Enmascara secretos y compacta espacios. Para texto plano de memoria."""
    if not text:
        return text
    scrubbed = text
    for pattern, repl in _REDACTION_RULES:
        scrubbed = pattern.sub(repl, scrubbed)
    scrubbed = " ".join(scrubbed.split())
    if len(scrubbed) > max_len:
        scrubbed = scrubbed[:max_len]
    return scrubbed


def scrub_secrets(text: str) -> str:
    """Enmascara secretos sin compactar espacios ni limitar longitud (logs estructurados)."""
    if not text:
        return text
    scrubbed = text
    for pattern, repl in _REDACTION_RULES:
        scrubbed = pattern.sub(repl, scrubbed)
    return scrubbed