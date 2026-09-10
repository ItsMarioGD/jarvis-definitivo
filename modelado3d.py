#!/usr/bin/env python3
"""
modelado3d.py - JARVIS modela en 3D con Blender (y hace "hologramas")
==================================================================
Pipeline:

    foto 2D  ─┬─► modelo image-to-3D (Meshy / Tripo por API, o TripoSR local) ─┐
              └─► si no hay ► el cerebro DESCRIBE la geometría como piezas ────┤
                                                                               ▼
                       Blender headless: importa/construye, centra, escala a 1 m,
                       suaviza, pone material PBR, exporta .glb/.obj/.stl y
                       renderiza un giro (MP4) + una foto (PNG).
                                                                               │
    "holograma" ───────────────────────────────────────────────────────────────┤
        · pirámide:  4 vistas a 90° compuestas para la pirámide de acrílico
                     que se pone sobre el móvil  ->  holograma_piramide.mp4
        · web:       visor tipo holograma (three.js), modelo girando con brillo

Sin GPU ni claves, la ruta de "imaginación" (piezas primitivas) funciona igual;
sale más tosco pero es un modelo real, local y editable en Blender.
"""
import json
import os
import re
import subprocess
import sys
import time

_SALIDA = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Modelos3D")
_SCRATCH = os.path.join(os.environ.get("TEMP", "/tmp"), "jarvis_blender")


# ── Blender ────────────────────────────────────────────────────────────────
def _blender() -> str:
    p = os.getenv("BLENDER_EXE", "").strip('"')
    if p and os.path.isfile(p):
        return p
    import glob
    for patron in (r"C:\Program Files\Blender Foundation\Blender *\blender.exe",
                   r"C:\Program Files\Blender Foundation\blender.exe",
                   "/usr/bin/blender", "/snap/bin/blender"):
        hits = sorted(glob.glob(patron), reverse=True)
        if hits:
            return hits[0]
    from shutil import which
    return which("blender") or ""


def disponible() -> bool:
    return bool(_blender())


def _run_blender(script: str, args: list, timeout: int = 600, log=print) -> dict:
    exe = _blender()
    if not exe:
        return {"ok": False, "error": "Blender no encontrado (pon BLENDER_EXE)"}
    os.makedirs(_SCRATCH, exist_ok=True)
    sp = os.path.join(_SCRATCH, f"job_{int(time.time()*1000)}.py")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(script)
    cmd = [exe, "-b", "--factory-startup", "-P", sp, "--", *map(str, args)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        cola = "\n".join((r.stdout or "").splitlines()[-8:])
        if r.returncode != 0:
            return {"ok": False, "error": (r.stderr or cola)[-500:]}
        return {"ok": True, "salida": cola}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Blender tardó más de {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        try:
            os.remove(sp)
        except OSError:
            pass


# ── receta de geometría por el cerebro ("imaginación") ─────────────────────
_PROMPT_GEO = (
    "Eres un modelador 3D. Describe el objeto como piezas primitivas para "
    "construirlo en Blender. Responde SOLO JSON:\n"
    '{"nombre":"...", "piezas":[{"forma":"cubo|esfera|cilindro|cono|toro|plano",'
    '"pos":[x,y,z],"escala":[sx,sy,sz],"rot_grados":[rx,ry,rz],'
    '"color":[r,g,b],"metal":0.0,"rugosidad":0.6}]}\n'
    "Unidades en metros, objeto centrado en el origen, altura total ~1. "
    "Entre 1 y 12 piezas. Colores 0-1."
)


def _geometria(core, descripcion: str, imagen_b64: str = "", log=print) -> dict:
    try:
        from openai import OpenAI
        _n, url, modelo, clave = core._proveedores()[0]
        cli = OpenAI(base_url=url, api_key=clave)
        contenido = [{"type": "text", "text": _PROMPT_GEO +
                      f"\n\nObjeto: {descripcion}"}]
        if imagen_b64:
            contenido.append({"type": "image_url",
                              "image_url": {"url": imagen_b64}})
        r = cli.chat.completions.create(
            model=modelo, temperature=0.3, max_tokens=1200,
            messages=[{"role": "user", "content": contenido if imagen_b64 else contenido[0]["text"]}])
        crudo = (r.choices[0].message.content or "")
        m = re.search(r"\{.*\}", crudo, re.DOTALL)
        receta = json.loads(m.group(0)) if m else {}
        if receta.get("piezas"):
            return receta
    except Exception as e:
        log(f"[3D] no pude sacar la geometría del cerebro: {e}")
    # Fallback mínimo: una caja, para no quedarnos sin nada.
    return {"nombre": re.sub(r"\W+", "_", descripcion)[:30] or "objeto",
            "piezas": [{"forma": "cubo", "pos": [0, 0, 0], "escala": [0.4, 0.4, 0.4],
                        "rot_grados": [0, 0, 0], "color": [0.6, 0.6, 0.65],
                        "metal": 0.1, "rugosidad": 0.5}]}


# ── image-to-3D por API (opcional) ────────────────────────────────────────
def _malla_por_api(ruta_img: str, log=print) -> str:
    """Devuelve la ruta a un .glb descargado, o '' si no hay clave/servicio."""
    key = os.getenv("MESHY_API_KEY", "")
    if not key:
        return ""
    try:
        import requests, base64
        with open(ruta_img, "rb") as f:
            data_uri = "data:image/png;base64," + base64.b64encode(f.read()).decode()
        h = {"Authorization": f"Bearer {key}"}
        r = requests.post("https://api.meshy.ai/openapi/v1/image-to-3d",
                          headers=h, json={"image_url": data_uri,
                                           "enable_pbr": True}, timeout=30)
        tid = r.json().get("result")
        if not tid:
            return ""
        for _ in range(120):
            time.sleep(5)
            s = requests.get(f"https://api.meshy.ai/openapi/v1/image-to-3d/{tid}",
                             headers=h, timeout=30).json()
            if s.get("status") == "SUCCEEDED":
                glb = s.get("model_urls", {}).get("glb")
                if glb:
                    out = os.path.join(_SCRATCH, f"meshy_{tid}.glb")
                    os.makedirs(_SCRATCH, exist_ok=True)
                    with open(out, "wb") as f:
                        f.write(requests.get(glb, timeout=120).content)
                    return out
            if s.get("status") in ("FAILED", "EXPIRED"):
                return ""
    except Exception as e:
        log(f"[3D] API image-to-3D falló: {e}")
    return ""


# ── scripts de Blender ───────────────────────────────────────────────────
_SB_CONSTRUIR = r'''
import bpy, sys, json, math, os
argv = sys.argv[sys.argv.index("--")+1:]
receta_path, malla_path, out_dir = argv[0], argv[1], argv[2]
os.makedirs(out_dir, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)

def nuevo_mat(nombre, color, metal, rug):
    m = bpy.data.materials.new(nombre); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1)
        if "Metallic" in b.inputs: b.inputs["Metallic"].default_value = float(metal)
        if "Roughness" in b.inputs: b.inputs["Roughness"].default_value = float(rug)
    return m

objs = []
if malla_path and os.path.isfile(malla_path):
    ext = malla_path.lower().rsplit(".",1)[-1]
    if ext == "glb" or ext == "gltf":
        bpy.ops.import_scene.gltf(filepath=malla_path)
    elif ext == "obj":
        bpy.ops.wm.obj_import(filepath=malla_path)
    elif ext == "stl":
        bpy.ops.wm.stl_import(filepath=malla_path)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
else:
    receta = json.load(open(receta_path, encoding="utf-8"))
    for i, p in enumerate(receta.get("piezas", [])):
        f = p.get("forma", "cubo")
        if f == "esfera":   bpy.ops.mesh.primitive_uv_sphere_add()
        elif f == "cilindro": bpy.ops.mesh.primitive_cylinder_add()
        elif f == "cono":   bpy.ops.mesh.primitive_cone_add()
        elif f == "toro":   bpy.ops.mesh.primitive_torus_add()
        elif f == "plano":  bpy.ops.mesh.primitive_plane_add()
        else:               bpy.ops.mesh.primitive_cube_add()
        o = bpy.context.active_object
        o.location = p.get("pos", [0,0,0])
        o.scale = p.get("escala", [1,1,1])
        r = p.get("rot_grados", [0,0,0])
        o.rotation_euler = [math.radians(x) for x in r]
        o.data.materials.append(nuevo_mat(f"m{i}", p.get("color",[0.7,0.7,0.7]),
                                          p.get("metal",0.0), p.get("rugosidad",0.6)))
        objs.append(o)

for o in objs:
    for pol in o.data.polygons: pol.use_smooth = True

# Unir, centrar y escalar a ~1 m de alto
if objs:
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1: bpy.ops.object.join()
    ob = bpy.context.active_object
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    ob.location = (0,0,0)
    dz = ob.dimensions.z or 1.0
    ob.scale = [s * (1.0/dz) for s in ob.scale]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    # Decimar si es enorme
    if len(ob.data.polygons) > 200000:
        mod = ob.modifiers.new("dec","DECIMATE"); mod.ratio = 0.3
        bpy.ops.object.modifier_apply(modifier=mod.name)

# Exportar
base = os.path.join(out_dir, "modelo")
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=base+".glb", export_format="GLB")
try: bpy.ops.wm.obj_export(filepath=base+".obj")
except Exception: pass
try: bpy.ops.wm.stl_export(filepath=base+".stl")
except Exception: pass

# Escena de render
bpy.ops.object.light_add(type="AREA", location=(3,-3,4)); bpy.context.active_object.data.energy = 800
bpy.ops.object.light_add(type="AREA", location=(-3,-2,2)); bpy.context.active_object.data.energy = 300
cam_data = bpy.data.cameras.new("cam"); cam = bpy.data.objects.new("cam", cam_data)
bpy.context.scene.collection.objects.link(cam); bpy.context.scene.camera = cam
import mathutils
piv = bpy.data.objects.new("piv", None); bpy.context.scene.collection.objects.link(piv)
cam.parent = piv; cam.location = (0,-3.2,1.6)
cam.rotation_euler = (math.radians(64),0,0)
sc = bpy.context.scene
def _motor():
    disp = [i.identifier for i in sc.render.bl_rna.properties['engine'].enum_items]
    for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "BLENDER_WORKBENCH"):
        if e in disp:
            return e
    return disp[0]
sc.render.engine = _motor()
sc.render.resolution_x = 960; sc.render.resolution_y = 960
sc.render.film_transparent = False
sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.02,0.02,0.03,1)

# Foto hero
sc.render.image_settings.file_format = "PNG"
sc.render.filepath = base + "_hero.png"
piv.rotation_euler = (0,0,math.radians(35))
bpy.ops.render.render(write_still=True)

# Giro: secuencia PNG girando el pivote a mano (sin FFMPEG ni acciones).
N = 36
frdir = os.path.join(out_dir, "giro")
os.makedirs(frdir, exist_ok=True)
for i in range(N):
    piv.rotation_euler = (0, 0, math.radians(360.0 * i / N))
    sc.render.filepath = os.path.join(frdir, "f%03d.png" % i)
    bpy.ops.render.render(write_still=True)
print("JARVIS3D_OK", base)
'''

_SB_HOLO_PIRAMIDE = r'''
import bpy, sys, os, math
argv = sys.argv[sys.argv.index("--")+1:]
glb, frdir = argv[0], argv[1]
os.makedirs(frdir, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
objs = [o for o in bpy.context.scene.objects if o.type=="MESH"]
if objs:
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs)>1: bpy.ops.object.join()
    ob = bpy.context.active_object
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    ob.location=(0,0,0)
    for m in ob.data.materials:
        if m and m.use_nodes:
            b = m.node_tree.nodes.get("Principled BSDF")
            if b and "Emission Color" in b.inputs:
                b.inputs["Emission Color"].default_value = list(b.inputs["Base Color"].default_value)
                if "Emission Strength" in b.inputs: b.inputs["Emission Strength"].default_value = 0.6
bpy.ops.object.light_add(type="SUN"); bpy.context.active_object.data.energy = 4
bpy.ops.object.light_add(type="AREA", location=(0,-3,3)); bpy.context.active_object.data.energy = 400
sc = bpy.context.scene
_disp = [i.identifier for i in sc.render.bl_rna.properties['engine'].enum_items]
sc.render.engine = next((e for e in ("BLENDER_EEVEE_NEXT","BLENDER_EEVEE","BLENDER_WORKBENCH")
                         if e in _disp), _disp[0])
sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0,0,0,1)
sc.render.resolution_x = 540; sc.render.resolution_y = 540
sc.render.film_transparent = True
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
cam_d = bpy.data.cameras.new("c"); cam = bpy.data.objects.new("c", cam_d)
sc.collection.objects.link(cam); sc.camera = cam
piv = bpy.data.objects.new("p", None); sc.collection.objects.link(piv)
cam.parent = piv; cam.location = (0,-2.6,1.35); cam.rotation_euler=(math.radians(62),0,0)

# Una sola vuelta limpia sobre fondo transparente; el layout en cruz de la
# pirámide lo compone Python (Pillow) después, que es más robusto.
N = 48
for i in range(N):
    piv.rotation_euler = (0, 0, math.radians(360.0 * i / N))
    sc.render.filepath = os.path.join(frdir, "h%03d.png" % i)
    bpy.ops.render.render(write_still=True)
print("JARVIS3D_OK", frdir)
'''


def _piramide_frames(frdir: str, out_dir: str, log=print) -> str:
    """Compone las vistas en cruz para la pirámide de acrílico (Pillow)."""
    import glob
    src = sorted(glob.glob(os.path.join(frdir, "*.png")))
    if not src:
        return ""
    try:
        from PIL import Image
    except Exception:
        log("[3D] sin Pillow: dejo las vistas sueltas; monta el cruce a mano")
        return frdir
    pdir = os.path.join(out_dir, "piramide_frames")
    os.makedirs(pdir, exist_ok=True)
    for i, f in enumerate(src):
        vista = Image.open(f).convert("RGBA")
        w, h = vista.size
        lienzo = Image.new("RGBA", (w * 3, h * 3), (0, 0, 0, 255))
        # abajo (0), arriba (180), izquierda (90), derecha (270)
        lienzo.alpha_composite(vista, (w, h * 2))
        lienzo.alpha_composite(vista.rotate(180), (w, 0))
        lienzo.alpha_composite(vista.rotate(90), (0, h))
        lienzo.alpha_composite(vista.rotate(270), (w * 2, h))
        lienzo.convert("RGB").save(os.path.join(pdir, "p%03d.png" % i))
    return pdir


def _a_animacion(frdir: str, salida_sin_ext: str, fps: int = 24, log=print) -> str:
    """Junta una carpeta de PNG en un vídeo/GIF. Devuelve la ruta, o '' si solo
    quedaron los frames."""
    import glob
    frames = sorted(glob.glob(os.path.join(frdir, "*.png")))
    if not frames:
        return ""
    # 1) mp4 con imageio-ffmpeg si está
    try:
        import imageio.v2 as imageio
        out = salida_sin_ext + ".mp4"
        with imageio.get_writer(out, fps=fps, codec="libx264", quality=8) as w:
            for f in frames:
                w.append_data(imageio.imread(f))
        return out
    except Exception:
        pass
    # 2) GIF/WEBP animado con Pillow
    try:
        from PIL import Image
        ims = [Image.open(f).convert("RGB") for f in frames]
        out = salida_sin_ext + ".webp"
        ims[0].save(out, save_all=True, append_images=ims[1:], duration=int(1000 / fps),
                    loop=0, method=4)
        return out
    except Exception as e:
        log(f"[3D] no pude juntar la animación ({e}); dejo los frames en {frdir}")
        return ""


# ── HTML holograma (three.js) ────────────────────────────────────────────
def _holo_web(glb_path: str, out_html: str, nombre: str) -> str:
    glb_rel = os.path.basename(glb_path)
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Holograma - {nombre}</title>
<style>html,body{{margin:0;height:100%;background:#04060a;overflow:hidden;font-family:system-ui}}
#t{{position:fixed;left:12px;bottom:10px;color:#5fd6ff;letter-spacing:3px;
font-size:13px;text-transform:uppercase;opacity:.8}}</style>
<script type="importmap">
{{"imports":{{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
"three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}}}
</script></head><body>
<div id="t">JARVIS - {nombre}</div>
<script type="module">
import * as THREE from 'three';
import {{GLTFLoader}} from 'three/addons/loaders/GLTFLoader.js';
const S=new THREE.Scene();
const C=new THREE.PerspectiveCamera(45,innerWidth/innerHeight,.1,100);C.position.set(0,.6,4);
const R=new THREE.WebGLRenderer({{antialias:true}});R.setSize(innerWidth,innerHeight);
document.body.appendChild(R.domElement);
S.add(new THREE.HemisphereLight(0x88ccff,0x0a0f18,1.1));
const p=new THREE.PointLight(0x66e0ff,3,20);p.position.set(3,4,3);S.add(p);
let M;
new GLTFLoader().load('{glb_rel}',g=>{{M=g.scene;
 const box=new THREE.Box3().setFromObject(M),c=box.getCenter(new THREE.Vector3()),
 sz=box.getSize(new THREE.Vector3()),k=1.8/Math.max(sz.x,sz.y,sz.z);
 M.position.sub(c);M.scale.setScalar(k);
 M.traverse(o=>{{if(o.isMesh){{o.material=new THREE.MeshStandardMaterial(
  {{color:0x2ec6ff,emissive:0x0a3550,metalness:.3,roughness:.35,transparent:true,opacity:.92}});
  const w=new THREE.LineSegments(new THREE.EdgesGeometry(o.geometry),
   new THREE.LineBasicMaterial({{color:0x9ff0ff}}));o.add(w);}}}});
 S.add(M);}},undefined,()=>{{document.getElementById('t').textContent='no pude cargar {glb_rel}';}});
const grid=new THREE.GridHelper(12,24,0x0e3a52,0x0a2536);grid.position.y=-1.1;S.add(grid);
addEventListener('resize',()=>{{C.aspect=innerWidth/innerHeight;C.updateProjectionMatrix();
 R.setSize(innerWidth,innerHeight);}});
(function loop(t){{requestAnimationFrame(loop);if(M)M.rotation.y=t*0.0006;
 p.position.x=Math.sin(t*0.001)*4;R.render(S,C);}})(0);
</script></body></html>"""
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    return out_html


# ── API pública ─────────────────────────────────────────────────────────
def _carpeta(nombre: str) -> str:
    slug = re.sub(r"\W+", "-", (nombre or "modelo").lower()).strip("-")[:40] or "modelo"
    d = os.path.join(_SALIDA, f"{slug}-{time.strftime('%Y%m%d-%H%M%S')}")
    os.makedirs(d, exist_ok=True)
    return d


def modelar(core, entrada: str, log=print) -> str:
    """entrada: ruta a una imagen, o una descripción de texto."""
    if not disponible():
        return ("Señor, no encuentro Blender. Instálelo o defina BLENDER_EXE con "
                "la ruta a blender.exe.")
    entrada = (entrada or "").strip().strip('"')
    es_img = os.path.isfile(entrada) and entrada.lower().endswith(
        (".png", ".jpg", ".jpeg", ".webp", ".bmp"))
    nombre = os.path.splitext(os.path.basename(entrada))[0] if es_img else entrada
    out_dir = _carpeta(nombre)
    receta_path = os.path.join(out_dir, "receta.json")
    malla_path = ""

    if es_img:
        malla_path = _malla_por_api(entrada, log=log)
        if not malla_path:
            # "imaginación": el cerebro mira la foto y describe la geometría
            try:
                import base64
                with open(entrada, "rb") as f:
                    b64 = "data:image/png;base64," + base64.b64encode(f.read()).decode()
            except Exception:
                b64 = ""
            receta = _geometria(core, f"lo que se ve en la foto {os.path.basename(entrada)}",
                                imagen_b64=b64, log=log)
            json.dump(receta, open(receta_path, "w", encoding="utf-8"), ensure_ascii=False)
    else:
        receta = _geometria(core, entrada, log=log)
        json.dump(receta, open(receta_path, "w", encoding="utf-8"), ensure_ascii=False)

    r = _run_blender(_SB_CONSTRUIR, [receta_path, malla_path, out_dir],
                     timeout=720, log=log)
    if not r["ok"]:
        return f"Señor, Blender falló al modelar: {r['error'][:200]}"
    glb = os.path.join(out_dir, "modelo.glb")
    _holo_web(glb, os.path.join(out_dir, "holograma.html"), nombre)
    giro = _a_animacion(os.path.join(out_dir, "giro"),
                        os.path.join(out_dir, "modelo_giro"), fps=24, log=log)
    metodo = ("escaneo por API" if malla_path else
              "reconstrucción a partir de la imagen" if es_img else
              "composición desde la descripción")
    giro_txt = f", un giro ({os.path.basename(giro)})" if giro else \
               " (los fotogramas del giro están en la subcarpeta giro/)"
    return (f"Listo, señor. Modelé «{nombre}» ({metodo}). En {out_dir}: "
            f"modelo.glb / .obj / .stl, una foto (modelo_hero.png){giro_txt} y "
            f"un visor holográfico (holograma.html). Diga «hazme un holograma de "
            "eso» para la versión pirámide.")


def holograma(core, entrada: str = "", log=print) -> str:
    """entrada: ruta a un .glb, o vacío para usar el último modelo."""
    entrada = (entrada or "").strip().strip('"')
    glb = ""
    if entrada.lower().endswith((".glb", ".gltf")) and os.path.isfile(entrada):
        glb = entrada
    else:
        # último modelo generado
        try:
            dirs = sorted((os.path.join(_SALIDA, d) for d in os.listdir(_SALIDA)),
                          key=os.path.getmtime, reverse=True)
            for d in dirs:
                cand = os.path.join(d, "modelo.glb")
                if os.path.isfile(cand):
                    glb = cand
                    break
        except Exception:
            pass
    if not glb:
        return ("Señor, no tengo ningún modelo. Primero pídame «modélame esto en "
                "3D» con una foto o una descripción.")
    if not disponible():
        return "Señor, necesito Blender para renderizar el holograma."
    out_dir = os.path.dirname(glb)
    frdir = os.path.join(out_dir, "holo_vistas")
    r = _run_blender(_SB_HOLO_PIRAMIDE, [glb, frdir], timeout=900, log=log)
    web = os.path.join(out_dir, "holograma.html")
    if not os.path.isfile(web):
        _holo_web(glb, web, os.path.basename(out_dir))
    if not r["ok"]:
        return (f"El visor web está en {web}, pero el render pirámide falló: "
                f"{r['error'][:160]}")
    pdir = _piramide_frames(frdir, out_dir, log=log)
    vid = _a_animacion(pdir, os.path.join(out_dir, "holograma_piramide"),
                       fps=24, log=log) if pdir else ""
    destino = vid or pdir or frdir
    return (f"Holograma listo, señor. {destino}: a pantalla completa en el móvil, "
            "con una pirámide de acrílico encima (las 4 vistas en cruz sobre "
            f"fondo negro). Y el visor web {web} para el navegador.")
