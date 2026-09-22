#!/usr/bin/env python3
"""
afinar.py - Afinar el modelo con tu propia forma de hablar (LoRA)
=================================================================
Hoy la personalidad de JARVIS es un prompt que se reescribe en cada arranque.
Funciona, pero tiene un techo: el modelo no sabe como hablas TU, ni que
significa «lo de siempre», ni tus abreviaturas.

Un ajuste fino con LoRA sobre el modelo local mete todo eso en los pesos. Este
modulo hace la parte que se puede hacer sin GPU y prepara la que la necesita:

    python afinar.py exportar     saca tu historial a un dataset JSONL limpio
    python afinar.py comprobar    dice si este equipo puede entrenar y con que
    python afinar.py guion        genera el script de entrenamiento listo

El entrenamiento en si NO se lanza a ciegas: necesita GPU con VRAM suficiente y
media hora larga, asi que se deja preparado y se ejecuta cuando el señor
quiera. El dataset se filtra antes: fuera credenciales, rutas privadas y
conversaciones marcadas como sensibles.
"""
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

RAIZ = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Afinado")
MIN_EJEMPLOS = 200

# Nunca deben entrar en un dataset de entrenamiento.
PATRONES_SENSIBLES = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[correo]"),
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[tarjeta]"),
    (re.compile(r"\b(sk|pk|ghp|xox[baprs])[-_][A-Za-z0-9]{16,}\b"), "[clave]"),
    (re.compile(r"\b[A-Z]:\\Users\\[^\\\s]+"), r"C:\\Users\\usuario"),
    (re.compile(r"\b\d{9}\b"), "[telefono]"),
]
PALABRAS_VETO = ("contraseña", "password", "pin ", "iban", "seed", "clave privada")


def _limpiar(texto: str) -> str:
    for patron, reemplazo in PATRONES_SENSIBLES:
        texto = patron.sub(reemplazo, texto)
    return texto.strip()


def _memoria(db: str):
    """Pares (usuario, asistente) del historial de conversaciones."""
    if not os.path.exists(db):
        return []
    con = sqlite3.connect(db)
    try:
        filas = con.execute(
            "SELECT role, content FROM interactions ORDER BY id").fetchall()
    except Exception:
        return []
    finally:
        con.close()

    pares, pendiente = [], None
    for rol, contenido in filas:
        if rol == "user":
            pendiente = contenido
        elif rol == "assistant" and pendiente:
            pares.append((pendiente, contenido))
            pendiente = None
    return pares


def _valoradas(signo: int) -> set:
    """Ordenes que el señor marco bien o mal. Sin feedback, conjunto vacio."""
    try:
        import feedback
        return feedback.ordenes_valoradas(signo, log=lambda *a: None)
    except Exception:
        return set()


def _parecidas(orden: str, marcadas: set) -> bool:
    """La misma orden dicha de otra forma sigue siendo la misma orden."""
    o = (orden or "").strip().lower()[:100]
    if o in marcadas:
        return True
    palabras = {p for p in re.split(r"\W+", o) if len(p) > 3}
    if not palabras:
        return False
    for m in marcadas:
        suyas = {p for p in re.split(r"\W+", m) if len(p) > 3}
        if suyas and len(palabras & suyas) / len(palabras | suyas) >= 0.7:
            return True
    return False


def exportar(log=print) -> str:
    """Escribe el dataset JSONL con tus conversaciones, ya anonimizado.

    Aprender de todo por igual seria aprender tambien los errores. Lo que el
    señor marco como malo se queda fuera; lo que marco como bueno cuenta el
    doble, que es la forma barata de darle peso sin tocar el entrenamiento.
    """
    pares = _memoria(os.path.join(RAIZ, "jarvis_memory.db"))
    pares += _memoria(os.path.join(RAIZ, "ultron_memory.db"))

    malas = _valoradas(-1)
    buenas = _valoradas(1)

    ejemplos, descartados, vetadas, repetidas = [], 0, 0, 0
    for usuario, asistente in pares:
        if not usuario or not asistente:
            continue
        texto = (usuario + " " + asistente).lower()
        if any(p in texto for p in PALABRAS_VETO):
            descartados += 1
            continue
        if len(usuario) < 4 or len(asistente) < 4:
            continue
        if malas and _parecidas(usuario, malas):
            vetadas += 1
            continue
        ejemplo = {
            "messages": [
                {"role": "user", "content": _limpiar(usuario)[:1500]},
                {"role": "assistant", "content": _limpiar(asistente)[:1500]},
            ]
        }
        ejemplos.append(ejemplo)
        if buenas and _parecidas(usuario, buenas):
            ejemplos.append(ejemplo)
            repetidas += 1

    os.makedirs(SALIDA, exist_ok=True)
    ruta = os.path.join(SALIDA, f"dataset_{datetime.now():%Y%m%d}.jsonl")
    with open(ruta, "w", encoding="utf-8") as f:
        for ejemplo in ejemplos:
            f.write(json.dumps(ejemplo, ensure_ascii=False) + "\n")

    log(f"[AFINAR] {len(ejemplos)} ejemplos exportados a {ruta}"
        + (f" ({descartados} descartados por contener datos sensibles)"
           if descartados else "")
        + (f", {vetadas} fuera por estar mal valorados" if vetadas else "")
        + (f", {repetidas} reforzados por estar bien valorados" if repetidas else ""))
    if len(ejemplos) < MIN_EJEMPLOS:
        log(f"[AFINAR] Con menos de {MIN_EJEMPLOS} ejemplos el ajuste no merece "
            "la pena todavía: siga usando el asistente unas semanas.")
    return ruta


def comprobar(log=print) -> dict:
    """¿Puede este equipo entrenar? Qué falta y con qué tamaño de modelo."""
    info = {"gpu": "", "vram_gb": 0.0, "torch": False, "unsloth": False,
            "recomendacion": ""}
    try:
        import torch
        info["torch"] = True
        if torch.cuda.is_available():
            info["gpu"] = torch.cuda.get_device_name(0)
            info["vram_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / 1024 ** 3, 1)
    except Exception:
        pass
    try:
        import unsloth  # noqa: F401
        info["unsloth"] = True
    except Exception:
        pass

    vram = info["vram_gb"]
    if not info["torch"]:
        info["recomendacion"] = ("Falta PyTorch con CUDA. Sin GPU el ajuste fino "
                                 "tardaría días: mejor seguir con el prompt.")
    elif vram >= 16:
        info["recomendacion"] = "Puede afinar un modelo de 7B con LoRA sin problemas."
    elif vram >= 8:
        info["recomendacion"] = "Le da para 3B o 4B con LoRA en 4 bits."
    elif vram > 0:
        info["recomendacion"] = ("VRAM justa: pruebe un modelo de 1B o use el "
                                 "prompt, que ya funciona.")
    else:
        info["recomendacion"] = ("No detecto GPU. El ajuste fino no es realista "
                                 "aquí; el prompt y la memoria dan casi lo mismo.")
    log(f"[AFINAR] {info['recomendacion']}")
    return info


GUION = '''#!/usr/bin/env python3
"""
Entrenamiento LoRA de {modelo} con el dataset de {dataset}.
Generado por afinar.py el {fecha}.

    pip install unsloth trl peft transformers datasets
    python {nombre}

Al terminar deja el adaptador en {salida}. Para usarlo con Ollama:
    ollama create jarvis-tuyo -f Modelfile     (FROM {modelo} + ADAPTER)
"""
from datasets import load_dataset
from trl import SFTTrainer, SFTConfig
from unsloth import FastLanguageModel

MODELO = "{modelo}"
DATASET = r"{dataset}"
SALIDA = r"{salida}"

modelo, tokenizador = FastLanguageModel.from_pretrained(
    model_name=MODELO, max_seq_length=2048, load_in_4bit=True)

modelo = FastLanguageModel.get_peft_model(
    modelo, r=16, lora_alpha=32, lora_dropout=0.0,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"])

datos = load_dataset("json", data_files=DATASET, split="train")

entrenador = SFTTrainer(
    model=modelo, tokenizer=tokenizador, train_dataset=datos,
    args=SFTConfig(output_dir=SALIDA, num_train_epochs=2,
                   per_device_train_batch_size=2, gradient_accumulation_steps=4,
                   learning_rate=2e-4, logging_steps=10, save_strategy="epoch"))
entrenador.train()
modelo.save_pretrained(SALIDA)
tokenizador.save_pretrained(SALIDA)
print("Adaptador guardado en", SALIDA)
'''


def guion(dataset: str = "", log=print) -> str:
    """Genera el script de entrenamiento, listo para ejecutar cuando toque."""
    if not dataset:
        dataset = exportar(log=log)
    modelo = os.getenv("JARVIS_AFINAR_BASE", "unsloth/Qwen2.5-3B-Instruct")
    salida = os.path.join(SALIDA, "adaptador")
    nombre = os.path.join(SALIDA, "entrenar_lora.py")
    with open(nombre, "w", encoding="utf-8") as f:
        f.write(GUION.format(modelo=modelo, dataset=dataset, salida=salida,
                             fecha=datetime.now().strftime("%Y-%m-%d"),
                             nombre=os.path.basename(nombre)))
    log(f"[AFINAR] Guion de entrenamiento en {nombre}")
    return nombre


def estado(log=print) -> dict:
    """Cuanto material hay y si el equipo aguanta el entrenamiento."""
    pares = _memoria(os.path.join(RAIZ, "jarvis_memory.db"))
    pares += _memoria(os.path.join(RAIZ, "ultron_memory.db"))
    equipo = comprobar(log=lambda *a: None)
    datasets = []
    if os.path.isdir(SALIDA):
        datasets = sorted(f for f in os.listdir(SALIDA) if f.endswith(".jsonl"))
    return {
        "conversaciones": len(pares),
        "minimo": MIN_EJEMPLOS,
        "suficiente": len(pares) >= MIN_EJEMPLOS,
        "mal_valoradas": len(_valoradas(-1)),
        "bien_valoradas": len(_valoradas(1)),
        "datasets": datasets,
        "adaptador": os.path.isdir(os.path.join(SALIDA, "adaptador")),
        "equipo": equipo,
    }


def resumen(log=print) -> str:
    e = estado(log=log)
    partes = [f"Tengo {e['conversaciones']} conversaciones suyas para aprender, señor"]
    if not e["suficiente"]:
        partes[0] += (f", y con menos de {e['minimo']} el ajuste no compensa "
                      "todavía")
    if e["bien_valoradas"] or e["mal_valoradas"]:
        partes.append(f"{e['bien_valoradas']} bien valoradas y "
                      f"{e['mal_valoradas']} mal, que quedan fuera")
    partes.append(e["equipo"]["recomendacion"].rstrip("."))
    return ". ".join(partes) + "."


def main(argv) -> int:
    accion = (argv[0].lower() if argv else "comprobar")
    if accion.startswith("export"):
        exportar()
    elif accion.startswith("comprob"):
        info = comprobar()
        print(json.dumps(info, ensure_ascii=False, indent=2))
    elif accion.startswith("guion") or accion.startswith("script"):
        guion()
    elif accion.startswith("estado") or accion.startswith("resumen"):
        print(resumen())
    else:
        print(__doc__.strip())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
