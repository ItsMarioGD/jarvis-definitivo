#!/usr/bin/env python3
"""
modelado3d.py - JARVIS modela en 3D en LOCAL y lo muestra como holograma
======================================================================
Sin APIs de pago. JARVIS tiene control del PC: abre lo que necesita, trabaja y
te enseña el resultado como holograma.

Flujo
-----
    foto / vídeo / texto / archivo de modelado
        │
        ├─ reconstrucción LOCAL (el primero que esté instalado):
        │     TripoSR  ·  Hunyuan3D  ·  ComfyUI (workflow 3D)  ·  Meshroom (vídeo/fotos)
        │     └─ si no hay ninguno ► "imaginación": el cerebro describe la
        │        geometría y Blender la construye con primitivas.
        │
        ├─ Blender headless: normaliza CUALQUIER formato
        │     (.blend .obj .fbx .stl .ply .dae .gltf .glb .x3d .abc .usd)
        │     a .glb, centra, escala, si hay esqueleto lo pone en T-pose,
        │     exporta .glb/.obj/.stl y renderiza foto + giro.
        │
        └─ Holograma: 48 vistas -> cruz para pirámide de acrílico + visor web
           (three.js). JARVIS abre el visor y, si quieres, Blender con la fuente.

Configuración en Prefs/modelado3d.json (se siembra en el primer uso):
    { "triposr_repo": "", "hunyuan_repo": "", "comfyui_url": "http://localhost:8188",
      "meshroom_bin": "", "blender_exe": "", "python_bin": "" }
"""
import glob
import json
import os
import re
import subprocess
import sys
import time

_SALIDA = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Modelos3D")
_SCRATCH = os.path.join(os.environ.get("TEMP", "/tmp"), "jarvis_blender")
_CFG = os.path.join(os.path.expanduser("~"), "Descargas", "JARVIS", "Prefs",
                    "modelado3d.json")

_FORMATOS_3D = (".blend", ".obj", ".fbx", ".stl", ".ply", ".dae", ".gltf",
                ".glb", ".x3d", ".abc", ".usd", ".usdz", ".usdc")
_FORMATOS_IMG = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
_FORMATOS_VID = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v")


# ── configuración / detección ──────────────────────────────────────────────
def _cfg() -> dict:
    base = {"triposr_repo": "", "hunyuan_repo": "",
            "comfyui_url": "http://localhost:8188", "comfyui_workflow": "",
            "meshroom_bin": "", "blender_exe": "", "python_bin": ""}
    try:
        with open(_CFG, encoding="utf-8") as f:
            base.update(json.load(f) or {})
    except Exception:
        try:
            os.makedirs(os.path.dirname(_CFG), exist_ok=True)
            with open(_CFG, "w", encoding="utf-8") as f:
                json.dump(base, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return base


def _blender() -> str:
    c = _cfg().get("blender_exe", "").strip('"')
    if c and os.path.isfile(c):
        return c
    for patron in (os.getenv("BLENDER_EXE", ""),
                   r"C:\Program Files\Blender Foundation\Blender *\blender.exe",
                   r"C:\Program Files\Blender Foundation\blender.exe",
                   "/usr/bin/blender", "/snap/bin/blender",
                   "/Applications/Blender.app/Contents/MacOS/Blender"):
        if not patron:
            continue
        hits = sorted(glob.glob(patron.strip('"')), reverse=True)
        if hits:
            return hits[0]
        if os.path.isfile(patron):
            return patron
    from shutil import which
    return which("blender") or ""


def _python() -> str:
    c = _cfg().get("python_bin", "").strip('"')
    return c if c and os.path.isfile(c) else sys.executable


def disponible() -> bool:
    return bool(_blender())


def backends() -> list:
    """Qué reconstructores locales hay instalados, en orden de preferencia."""
    c = _cfg()
    out = []
    if c.get("triposr_repo") and os.path.isdir(c["triposr_repo"]):
        out.append("triposr")
    if c.get("hunyuan_repo") and os.path.isdir(c["hunyuan_repo"]):
        out.append("hunyuan3d")
    if _comfyui_vivo(c.get("comfyui_url", "")):
        out.append("comfyui")
    if c.get("meshroom_bin") and os.path.isfile(c["meshroom_bin"]):
        out.append("meshroom")
    return out


def _comfyui_vivo(url: str) -> bool:
    if not url:
        return False
    try:
        import requests
        return requests.get(url.rstrip("/") + "/system_stats", timeout=2).status_code == 200
    except Exception:
        return False


# ── ejecutar Blender ───────────────────────────────────────────────────────
def _run_blender(script: str, args: list, timeout: int = 700, log=print) -> dict:
    exe = _blender()
    if not exe:
        return {"ok": False, "error": "Blender no encontrado (pon blender_exe en Prefs/modelado3d.json)"}
    os.makedirs(_SCRATCH, exist_ok=True)
    sp = os.path.join(_SCRATCH, f"job_{int(time.time()*1000)}.py")
    with open(sp, "w", encoding="utf-8") as f:
        f.write(script)
    try:
        r = subprocess.run([exe, "-b", "--factory-startup", "-P", sp, "--", *map(str, args)],
                           capture_output=True, text=True, timeout=timeout)
        cola = "\n".join((r.stdout or "").splitlines()[-8:])
        if r.returncode != 0 or "JARVIS3D_OK" not in (r.stdout or ""):
            return {"ok": False, "error": (r.stderr or cola)[-600:]}
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


# ── reconstructores locales ───────────────────────────────────────────────
def _bk_triposr(imagen: str, out_dir: str, log=print) -> str:
    c = _cfg()
    repo = c["triposr_repo"]
    py = _python()
    run = os.path.join(repo, "run.py")
    if not os.path.isfile(run):
        return ""
    try:
        subprocess.run([py, run, imagen, "--output-dir", out_dir,
                        "--model-save-format", "glb"],
                       cwd=repo, capture_output=True, text=True, timeout=900)
    except Exception as e:
        log(f"[3D] TripoSR falló: {e}")
        return ""
    hits = glob.glob(os.path.join(out_dir, "**", "*.glb"), recursive=True) or \
        glob.glob(os.path.join(out_dir, "**", "*.obj"), recursive=True)
    return hits[0] if hits else ""


def _bk_hunyuan(imagen: str, out_dir: str, log=print) -> str:
    c = _cfg()
    repo = c["hunyuan_repo"]
    py = _python()
    for cand in ("minimal_demo.py", "demo.py", "run.py"):
        script = os.path.join(repo, cand)
        if os.path.isfile(script):
            break
    else:
        return ""
    try:
        subprocess.run([py, script, "--image_path", imagen, "--output_path", out_dir],
                       cwd=repo, capture_output=True, text=True, timeout=1800)
    except Exception as e:
        log(f"[3D] Hunyuan3D falló: {e}")
        return ""
    hits = (glob.glob(os.path.join(out_dir, "**", "*.glb"), recursive=True) or
            glob.glob(os.path.join(out_dir, "**", "*.obj"), recursive=True))
    return hits[0] if hits else ""


def _bk_comfyui(imagen: str, out_dir: str, log=print) -> str:
    """Manda un workflow 3D a un ComfyUI que ya esté corriendo."""
    c = _cfg()
    url = c["comfyui_url"].rstrip("/")
    wf_path = c.get("comfyui_workflow", "")
    if not (wf_path and os.path.isfile(wf_path)):
        log("[3D] ComfyUI vivo pero sin comfyui_workflow en la config")
        return ""
    try:
        import requests
        with open(imagen, "rb") as f:
            up = requests.post(f"{url}/upload/image",
                               files={"image": (os.path.basename(imagen), f)},
                               timeout=30).json()
        nombre_img = up.get("name", os.path.basename(imagen))
        wf = json.load(open(wf_path, encoding="utf-8"))
        wf_txt = json.dumps(wf).replace("__IMAGEN__", nombre_img)
        pid = requests.post(f"{url}/prompt",
                            json={"prompt": json.loads(wf_txt)}, timeout=30).json().get("prompt_id")
        for _ in range(240):
            time.sleep(3)
            h = requests.get(f"{url}/history/{pid}", timeout=15).json()
            if pid in h:
                for _n, salida in h[pid].get("outputs", {}).items():
                    for clave in ("gltf", "glb", "mesh", "3d", "files"):
                        for item in salida.get(clave, []) or []:
                            fn = item.get("filename")
                            if fn and fn.lower().endswith((".glb", ".gltf", ".obj")):
                                data = requests.get(f"{url}/view", params={
                                    "filename": fn, "subfolder": item.get("subfolder", ""),
                                    "type": item.get("type", "output")}, timeout=120).content
                                dst = os.path.join(out_dir, fn)
                                open(dst, "wb").write(data)
                                return dst
                return ""
    except Exception as e:
        log(f"[3D] ComfyUI falló: {e}")
    return ""


def _bk_meshroom(carpeta_imgs: str, out_dir: str, log=print) -> str:
    c = _cfg()
    binm = c["meshroom_bin"]
    if not os.path.isfile(binm):
        return ""
    try:
        subprocess.run([binm, "-i", carpeta_imgs, "-o", out_dir],
                       capture_output=True, text=True, timeout=3600)
    except Exception as e:
        log(f"[3D] Meshroom falló: {e}")
        return ""
    hits = (glob.glob(os.path.join(out_dir, "**", "*.obj"), recursive=True) or
            glob.glob(os.path.join(out_dir, "**", "*.glb"), recursive=True))
    return hits[0] if hits else ""


def _reconstruir(imagen: str, out_dir: str, log=print) -> tuple[str, str]:
    """(ruta_malla, metodo). '' si ningún backend local pudo."""
    for bk in backends():
        log(f"[3D] intento con backend local: {bk}")
        r = ({"triposr": _bk_triposr, "hunyuan3d": _bk_hunyuan,
              "comfyui": _bk_comfyui}.get(bk, lambda *a, **k: ""))(imagen, out_dir, log=log)
        if r and os.path.isfile(r):
            return r, bk
    return "", ""


# ── vídeo -> fotogramas ──────────────────────────────────────────────────
def _frames_de_video(video: str, out_dir: str, n: int = 40, log=print) -> list:
    fr = os.path.join(out_dir, "frames")
    os.makedirs(fr, exist_ok=True)
    try:
        import imageio.v2 as imageio
        rdr = imageio.get_reader(video)
        total = rdr.count_frames() if hasattr(rdr, "count_frames") else 300
        paso = max(1, total // n)
        rutas = []
        for i, frm in enumerate(rdr):
            if i % paso == 0:
                p = os.path.join(fr, f"f{i:05d}.png")
                imageio.imwrite(p, frm)
                rutas.append(p)
        return rutas
    except Exception:
        pass
    try:
        import cv2
        cap = cv2.VideoCapture(video)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 300
        paso = max(1, total // n)
        rutas, i = [], 0
        while True:
            ok_, fr_img = cap.read()
            if not ok_:
                break
            if i % paso == 0:
                p = os.path.join(fr, f"f{i:05d}.png")
                cv2.imwrite(p, fr_img)
                rutas.append(p)
            i += 1
        cap.release()
        return rutas
    except Exception as e:
        log(f"[3D] no pude sacar fotogramas del vídeo ({e}); instala imageio-ffmpeg o opencv-python")
        return []


def _mas_nitida(rutas: list) -> str:
    try:
        from PIL import Image, ImageFilter
        mejor, score = rutas[0], -1
        for r in rutas:
            im = Image.open(r).convert("L").resize((256, 256))
            bordes = im.filter(ImageFilter.FIND_EDGES)
            s = sum(bordes.getdata())
            if s > score:
                mejor, score = r, s
        return mejor
    except Exception:
        return rutas[len(rutas) // 2] if rutas else ""


# ── geometría por "imaginación" (fallback sin backend) ──────────────────
_PROMPT_GEO = (
    "Eres un modelador 3D. Describe el objeto como piezas primitivas para "
    "Blender. SOLO JSON:\n"
    '{"nombre":"...","piezas":[{"forma":"cubo|esfera|cilindro|cono|toro|plano",'
    '"pos":[x,y,z],"escala":[sx,sy,sz],"rot_grados":[rx,ry,rz],'
    '"color":[r,g,b],"metal":0.0,"rugosidad":0.6}]}\n'
    "Metros, centrado en el origen, alto ~1. Entre 1 y 14 piezas. Colores 0-1."
)


def _geometria(core, descripcion: str, imagen_b64: str = "", log=print) -> dict:
    try:
        from openai import OpenAI
        _n, url, modelo, clave = core._proveedores()[0]
        cli = OpenAI(base_url=url, api_key=clave)
        txt = _PROMPT_GEO + f"\n\nObjeto: {descripcion}"
        cont = ([{"type": "text", "text": txt},
                 {"type": "image_url", "image_url": {"url": imagen_b64}}]
                if imagen_b64 else txt)
        r = cli.chat.completions.create(model=modelo, temperature=0.3, max_tokens=1300,
                                        messages=[{"role": "user", "content": cont}])
        m = re.search(r"\{.*\}", r.choices[0].message.content or "", re.DOTALL)
        rec = json.loads(m.group(0)) if m else {}
        if rec.get("piezas"):
            return rec
    except Exception as e:
        log(f"[3D] geometría del cerebro falló: {e}")
    return {"nombre": re.sub(r"\W+", "_", descripcion)[:30] or "objeto",
            "piezas": [{"forma": "cubo", "pos": [0, 0, 0], "escala": [0.4, 0.4, 0.4],
                        "rot_grados": [0, 0, 0], "color": [0.6, 0.6, 0.65],
                        "metal": 0.1, "rugosidad": 0.5}]}


# ── scripts de Blender ─────────────────────────────────────────────────
_SB_PREP = r'''
import bpy, sys, os, json, math
a = sys.argv[sys.argv.index("--")+1:]
modo, fuente, out_dir, t_pose = a[0], a[1], a[2], (a[3] == "1")
os.makedirs(out_dir, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)

def mat(nombre, color, metal, rug):
    m = bpy.data.materials.new(nombre); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1)
        if "Metallic" in b.inputs: b.inputs["Metallic"].default_value = float(metal)
        if "Roughness" in b.inputs: b.inputs["Roughness"].default_value = float(rug)
    return m

if modo == "receta":
    rec = json.load(open(fuente, encoding="utf-8"))
    for i, p in enumerate(rec.get("piezas", [])):
        f = p.get("forma", "cubo")
        {"esfera": bpy.ops.mesh.primitive_uv_sphere_add,
         "cilindro": bpy.ops.mesh.primitive_cylinder_add,
         "cono": bpy.ops.mesh.primitive_cone_add,
         "toro": bpy.ops.mesh.primitive_torus_add,
         "plano": bpy.ops.mesh.primitive_plane_add}.get(f, bpy.ops.mesh.primitive_cube_add)()
        o = bpy.context.active_object
        o.location = p.get("pos", [0,0,0]); o.scale = p.get("escala", [1,1,1])
        o.rotation_euler = [math.radians(x) for x in p.get("rot_grados", [0,0,0])]
        o.data.materials.append(mat(f"m{i}", p.get("color",[0.7,0.7,0.7]),
                                    p.get("metal",0.0), p.get("rugosidad",0.6)))
else:
    ext = fuente.lower().rsplit(".",1)[-1]
    if ext == "blend":
        bpy.ops.wm.open_mainfile(filepath=fuente)
    elif ext in ("glb","gltf"): bpy.ops.import_scene.gltf(filepath=fuente)
    elif ext == "obj":  bpy.ops.wm.obj_import(filepath=fuente)
    elif ext == "fbx":  bpy.ops.import_scene.fbx(filepath=fuente)
    elif ext == "stl":  bpy.ops.wm.stl_import(filepath=fuente)
    elif ext == "ply":  bpy.ops.wm.ply_import(filepath=fuente)
    elif ext == "dae":  bpy.ops.wm.collada_import(filepath=fuente)
    elif ext == "x3d":  bpy.ops.import_scene.x3d(filepath=fuente)
    elif ext == "abc":  bpy.ops.wm.alembic_import(filepath=fuente)
    elif ext in ("usd","usdz","usdc"): bpy.ops.wm.usd_import(filepath=fuente)
    else: raise SystemExit("formato no soportado: " + ext)

# T-pose: armadura a reposo y pose limpia
if t_pose:
    for ar in [o for o in bpy.data.objects if o.type == "ARMATURE"]:
        ar.data.pose_position = "REST"
        try:
            bpy.context.view_layer.objects.active = ar
            bpy.ops.object.mode_set(mode="POSE")
            bpy.ops.pose.select_all(action="SELECT")
            bpy.ops.pose.transforms_clear()
            bpy.ops.object.mode_set(mode="OBJECT")
        except Exception: pass

meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
for o in meshes:
    for pol in o.data.polygons: pol.use_smooth = True

if meshes:
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes: o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        try: bpy.ops.object.join()
        except Exception: pass
    ob = bpy.context.active_object
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    ob.location = (0,0,0)
    dz = ob.dimensions.z or 1.0
    ob.scale = [s*(1.0/dz) for s in ob.scale]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    # apoyar en el suelo
    minz = min((ob.matrix_world @ v.co).z for v in ob.data.vertices)
    ob.location.z -= minz
    bpy.ops.object.transform_apply(location=True)
    if len(ob.data.polygons) > 250000:
        md = ob.modifiers.new("d","DECIMATE"); md.ratio = 0.25
        bpy.ops.object.modifier_apply(modifier=md.name)

base = os.path.join(out_dir, "modelo")
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=base+".glb", export_format="GLB")
try: bpy.ops.wm.obj_export(filepath=base+".obj")
except Exception: pass
try: bpy.ops.wm.stl_export(filepath=base+".stl")
except Exception: pass
print("JARVIS3D_OK", base)
'''

_SB_RENDER = r'''
import bpy, sys, os, math
a = sys.argv[sys.argv.index("--")+1:]
glb, out_dir, holo = a[0], a[1], (a[2] == "holo")
os.makedirs(out_dir, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
ms = [o for o in bpy.context.scene.objects if o.type == "MESH"]
if ms:
    bpy.ops.object.select_all(action="DESELECT")
    for o in ms: o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1:
        try: bpy.ops.object.join()
        except Exception: pass
    ob = bpy.context.active_object
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    ob.location = (0,0,0)
sc = bpy.context.scene
_disp = [i.identifier for i in sc.render.bl_rna.properties['engine'].enum_items]
sc.render.engine = next((e for e in ("BLENDER_EEVEE_NEXT","BLENDER_EEVEE","BLENDER_WORKBENCH")
                         if e in _disp), _disp[0])
sc.world = bpy.data.worlds.new("w"); sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0,0,0,1) if holo else (0.02,0.02,0.03,1)
bpy.ops.object.light_add(type="AREA", location=(3,-3,4)); bpy.context.active_object.data.energy = 900
bpy.ops.object.light_add(type="AREA", location=(-3,-2,2)); bpy.context.active_object.data.energy = 350
cam_d = bpy.data.cameras.new("c"); cam = bpy.data.objects.new("c", cam_d)
sc.collection.objects.link(cam); sc.camera = cam
piv = bpy.data.objects.new("p", None); sc.collection.objects.link(piv)
cam.parent = piv; cam.location = (0,-3.0,1.5); cam.rotation_euler = (math.radians(64),0,0)
res = 540 if holo else 960
sc.render.resolution_x = res; sc.render.resolution_y = res
sc.render.image_settings.file_format = "PNG"
if holo:
    sc.render.film_transparent = True
    sc.render.image_settings.color_mode = "RGBA"

if not holo:
    sc.render.filepath = os.path.join(out_dir, "modelo_hero.png")
    piv.rotation_euler = (0,0,math.radians(35))
    bpy.ops.render.render(write_still=True)

N = 48 if holo else 36
fdir = os.path.join(out_dir, "holo_vistas" if holo else "giro")
os.makedirs(fdir, exist_ok=True)
for i in range(N):
    piv.rotation_euler = (0,0,math.radians(360.0*i/N))
    sc.render.filepath = os.path.join(fdir, ("h%03d.png" if holo else "f%03d.png") % i)
    bpy.ops.render.render(write_still=True)
print("JARVIS3D_OK", fdir)
'''


# ── holograma: composición y visor ────────────────────────────────────
def _piramide_frames(frdir: str, out_dir: str, log=print) -> str:
    src = sorted(glob.glob(os.path.join(frdir, "*.png")))
    if not src:
        return ""
    try:
        from PIL import Image
    except Exception:
        log("[3D] sin Pillow: dejo las 4 vistas sueltas para montar la cruz a mano")
        return frdir
    pdir = os.path.join(out_dir, "piramide_frames")
    os.makedirs(pdir, exist_ok=True)
    for i, f in enumerate(src):
        v = Image.open(f).convert("RGBA")
        w, h = v.size
        cv = Image.new("RGBA", (w*3, h*3), (0, 0, 0, 255))
        cv.alpha_composite(v, (w, h*2))
        cv.alpha_composite(v.rotate(180), (w, 0))
        cv.alpha_composite(v.rotate(90), (0, h))
        cv.alpha_composite(v.rotate(270), (w*2, h))
        cv.convert("RGB").save(os.path.join(pdir, "p%03d.png" % i))
    return pdir


def _a_animacion(frdir: str, salida_sin_ext: str, fps: int = 24, log=print) -> str:
    frames = sorted(glob.glob(os.path.join(frdir, "*.png")))
    if not frames:
        return ""
    try:
        import imageio.v2 as imageio
        out = salida_sin_ext + ".mp4"
        with imageio.get_writer(out, fps=fps, codec="libx264", quality=8) as w:
            for f in frames:
                w.append_data(imageio.imread(f))
        return out
    except Exception:
        pass
    try:
        from PIL import Image
        ims = [Image.open(f).convert("RGB") for f in frames]
        out = salida_sin_ext + ".webp"
        ims[0].save(out, save_all=True, append_images=ims[1:],
                    duration=int(1000/fps), loop=0, method=4)
        return out
    except Exception as e:
        log(f"[3D] sin pillow/imageio: quedan los fotogramas en {frdir} ({e})")
        return ""


def _holo_web(glb_path: str, out_html: str, nombre: str, modo: str = "completo") -> str:
    rel = os.path.basename(glb_path)
    pose = "T-pose" if modo == "t-pose" else "completo"
    html = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Holograma - {nombre}</title>
<style>html,body{{margin:0;height:100%;background:#04060a;overflow:hidden;font-family:system-ui}}
#t{{position:fixed;left:12px;bottom:10px;color:#5fd6ff;letter-spacing:3px;font-size:12px;
text-transform:uppercase;opacity:.8}}</style>
<script type="importmap">
{{"imports":{{"three":"https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
"three/addons/":"https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"}}}}
</script></head><body>
<div id="t">JARVIS - {nombre} - {pose}</div>
<script type="module">
import * as THREE from 'three';
import {{GLTFLoader}} from 'three/addons/loaders/GLTFLoader.js';
const S=new THREE.Scene();
const C=new THREE.PerspectiveCamera(45,innerWidth/innerHeight,.1,100);C.position.set(0,1.1,4.2);
const R=new THREE.WebGLRenderer({{antialias:true}});R.setSize(innerWidth,innerHeight);
document.body.appendChild(R.domElement);
S.add(new THREE.HemisphereLight(0x88ccff,0x0a0f18,1.15));
const p=new THREE.PointLight(0x66e0ff,3,25);p.position.set(3,5,3);S.add(p);
let M;
new GLTFLoader().load('{rel}',g=>{{M=g.scene;
 const box=new THREE.Box3().setFromObject(M),c=box.getCenter(new THREE.Vector3()),
 sz=box.getSize(new THREE.Vector3()),k=2.0/Math.max(sz.x,sz.y,sz.z);
 M.position.sub(c);M.scale.setScalar(k);M.position.y+= (sz.y*k)/2 - 1.0;
 M.traverse(o=>{{if(o.isMesh){{o.material=new THREE.MeshStandardMaterial(
  {{color:0x2ec6ff,emissive:0x0a3550,metalness:.3,roughness:.35,transparent:true,opacity:.92}});
  o.add(new THREE.LineSegments(new THREE.EdgesGeometry(o.geometry),
   new THREE.LineBasicMaterial({{color:0x9ff0ff}})));}}}});
 S.add(M);}},undefined,()=>{{document.getElementById('t').textContent='no pude cargar {rel}';}});
S.add(new THREE.GridHelper(14,28,0x0e3a52,0x0a2536));
addEventListener('resize',()=>{{C.aspect=innerWidth/innerHeight;C.updateProjectionMatrix();
 R.setSize(innerWidth,innerHeight);}});
(function loop(t){{requestAnimationFrame(loop);if(M)M.rotation.y=t*0.0006;
 p.position.x=Math.sin(t*0.001)*4;R.render(S,C);}})(0);
</script></body></html>"""
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html)
    return out_html


# ── abrir cosas (JARVIS tiene control del PC) ─────────────────────────
def _abrir(ruta: str, log=print):
    try:
        if hasattr(os, "startfile"):
            os.startfile(ruta)  # noqa: S606
            return True
        subprocess.Popen(["xdg-open" if sys.platform.startswith("linux") else "open", ruta])
        return True
    except Exception as e:
        log(f"[3D] no pude abrir {ruta}: {e}")
        return False


def abrir_blender_con(archivo: str, log=print) -> str:
    exe = _blender()
    if not exe:
        return "No encuentro Blender, señor."
    try:
        import ejecutor
        ejecutor.lanzar([exe, archivo] if archivo and os.path.isfile(archivo) else [exe],
                        origen="modelado3d", orden="abrir Blender", log=log)
        return "Abro Blender, señor."
    except Exception:
        _abrir(exe, log=log)
        return "Abro Blender, señor."


# ── API pública ─────────────────────────────────────────────────────
def _carpeta(nombre: str) -> str:
    slug = re.sub(r"\W+", "-", (nombre or "modelo").lower()).strip("-")[:40] or "modelo"
    d = os.path.join(_SALIDA, f"{slug}-{time.strftime('%Y%m%d-%H%M%S')}")
    os.makedirs(d, exist_ok=True)
    return d


def modelar(core, entrada: str, t_pose: bool = False, abrir: bool = True, log=print) -> str:
    if not disponible():
        return ("Señor, no encuentro Blender. Póngalo en Prefs/modelado3d.json "
                "(blender_exe) o instálelo.")
    entrada = (entrada or "").strip().strip('"')
    ext = os.path.splitext(entrada)[1].lower() if os.path.isfile(entrada) else ""
    nombre = os.path.splitext(os.path.basename(entrada))[0] if ext else entrada[:40]
    out = _carpeta(nombre)
    modo, fuente, metodo = "receta", "", ""

    if ext in _FORMATOS_3D:
        modo, fuente, metodo = "importar", entrada, "archivo de modelado"
    elif ext in _FORMATOS_VID:
        frames = _frames_de_video(entrada, out, log=log)
        if not frames:
            return ("Señor, no pude leer el vídeo. Instale imageio-ffmpeg o "
                    "opencv-python.")
        mroom = [b for b in backends() if b == "meshroom"]
        if mroom:
            m = _bk_meshroom(os.path.join(out, "frames"), os.path.join(out, "mr"), log=log)
            if m:
                modo, fuente, metodo = "importar", m, "fotogrametría del vídeo (Meshroom)"
        if not fuente:
            best = _mas_nitida(frames)
            m, bk = _reconstruir(best, out, log=log)
            if m:
                modo, fuente, metodo = "importar", m, f"mejor fotograma -> {bk}"
            else:
                metodo = "imaginación (sin reconstructor local)"
                rec = _geometria(core, f"lo que sale en el vídeo {nombre}", log=log)
                fuente = os.path.join(out, "receta.json")
                json.dump(rec, open(fuente, "w", encoding="utf-8"), ensure_ascii=False)
    elif ext in _FORMATOS_IMG:
        m, bk = _reconstruir(entrada, out, log=log)
        if m:
            modo, fuente, metodo = "importar", m, f"reconstrucción local ({bk})"
        else:
            try:
                import base64
                b64 = "data:image/png;base64," + base64.b64encode(open(entrada, "rb").read()).decode()
            except Exception:
                b64 = ""
            rec = _geometria(core, f"lo que se ve en la foto {nombre}", imagen_b64=b64, log=log)
            fuente = os.path.join(out, "receta.json")
            json.dump(rec, open(fuente, "w", encoding="utf-8"), ensure_ascii=False)
            metodo = "imaginación a partir de la imagen (sin reconstructor local)"
    else:
        rec = _geometria(core, entrada, log=log)
        fuente = os.path.join(out, "receta.json")
        json.dump(rec, open(fuente, "w", encoding="utf-8"), ensure_ascii=False)
        metodo = "composición desde la descripción"

    p = _run_blender(_SB_PREP, [modo, fuente, out, "1" if t_pose else "0"],
                     timeout=900, log=log)
    if not p["ok"]:
        return f"Señor, Blender falló al preparar el modelo: {p['error'][:200]}"
    glb = os.path.join(out, "modelo.glb")
    _run_blender(_SB_RENDER, [glb, out, "foto"], timeout=700, log=log)
    _a_animacion(os.path.join(out, "giro"), os.path.join(out, "modelo_giro"), log=log)
    web = _holo_web(glb, os.path.join(out, "holograma.html"), nombre,
                    "t-pose" if t_pose else "completo")
    if abrir:
        _abrir(web, log=log)
    return (f"Listo, señor. Modelé «{nombre}» por {metodo}"
            + (" en T-pose" if t_pose else "") + f". Todo en {out}: modelo.glb/.obj/"
            f".stl, modelo_hero.png, el giro y el visor holográfico (ya te lo abrí). "
            "Di «hazme el holograma pirámide de eso» para la versión de acrílico.")


def holograma(core, entrada: str = "", modo: str = "completo", abrir: bool = True,
              log=print) -> str:
    entrada = (entrada or "").strip().strip('"')
    ext = os.path.splitext(entrada)[1].lower() if os.path.isfile(entrada) else ""
    if ext in _FORMATOS_3D and ext not in (".glb", ".gltf"):
        # normalizar cualquier formato a glb
        out = _carpeta(os.path.splitext(os.path.basename(entrada))[0])
        p = _run_blender(_SB_PREP, ["importar", entrada, out,
                                    "1" if modo == "t-pose" else "0"], timeout=900, log=log)
        if not p["ok"]:
            return f"No pude convertir ese archivo, señor: {p['error'][:160]}"
        glb = os.path.join(out, "modelo.glb")
    elif ext in (".glb", ".gltf") and os.path.isfile(entrada):
        glb = entrada
        out = os.path.dirname(entrada)
    else:
        glb, out = "", ""
        try:
            for d in sorted((os.path.join(_SALIDA, x) for x in os.listdir(_SALIDA)),
                            key=os.path.getmtime, reverse=True):
                if os.path.isfile(os.path.join(d, "modelo.glb")):
                    glb, out = os.path.join(d, "modelo.glb"), d
                    break
        except Exception:
            pass
    if not glb:
        return ("Señor, no tengo ningún modelo. Pídame primero «modélame esto en "
                "3D» con una foto, un vídeo, una descripción o un archivo .blend/.obj/.fbx.")
    if not disponible():
        return "Señor, necesito Blender para el holograma."
    nombre = os.path.basename(out)
    r = _run_blender(_SB_RENDER, [glb, out, "holo"], timeout=900, log=log)
    web = os.path.join(out, "holograma.html")
    if not os.path.isfile(web):
        _holo_web(glb, web, nombre, modo)
    if not r["ok"]:
        if abrir:
            _abrir(web, log=log)
        return f"Te abrí el visor web {web}; el render de vistas falló: {r['error'][:150]}"
    pdir = _piramide_frames(os.path.join(out, "holo_vistas"), out, log=log)
    vid = _a_animacion(pdir, os.path.join(out, "holograma_piramide"), log=log) if pdir else ""
    if abrir:
        _abrir(web, log=log)
        if vid:
            _abrir(vid, log=log)
    destino = vid or pdir or os.path.join(out, "holo_vistas")
    return (f"Holograma listo, señor ({modo}). Visor web abierto ({web}). Para la "
            f"pirámide de acrílico: {destino} a pantalla completa en el móvil.")


def estado_backends() -> str:
    bs = backends()
    c = _cfg()
    partes = [f"Blender: {'sí' if disponible() else 'no'}"]
    partes.append("reconstructores locales: " + (", ".join(bs) if bs else "ninguno "
                  "(uso la 'imaginación' del cerebro)"))
    if not bs:
        partes.append("para reconstrucción real: instala TripoSR o Hunyuan3D y pon "
                      "su carpeta en Prefs/modelado3d.json, o levanta ComfyUI con un "
                      "workflow 3D.")
    return "Modelado 3D — " + ". ".join(partes) + "."
