# Modelado 3D local de JARVIS — puesta a punto

Sin APIs de pago. JARVIS usa Blender (ya instalado) + un reconstructor local
que tú elijas. Todo se configura en:

    %USERPROFILE%\Descargas\JARVIS\Prefs\modelado3d.json

```json
{
  "blender_exe": "",            // vacío = autodetecta (C:\Program Files\Blender Foundation\...)
  "python_bin": "",             // python para lanzar TripoSR/Hunyuan (vacío = el de JARVIS)
  "triposr_repo": "",           // carpeta del repo TripoSR clonado
  "hunyuan_repo": "",           // carpeta del repo Hunyuan3D
  "comfyui_url": "http://localhost:8188",
  "comfyui_workflow": "",       // .json de un workflow imagen->3D (con "__IMAGEN__" donde va el nombre de la imagen)
  "meshroom_bin": ""            // meshroom_batch.exe para fotogrametría de vídeo/fotos
}
```

Con **cero reconstructores**, JARVIS sigue funcionando: el cerebro *mira* la
foto/vídeo y describe la geometría con primitivas, y Blender la construye. Sale
más tosco pero es un modelo real y editable.

## Opciones por hardware (tu GPU: RTX 4050, 6 GB)

| Reconstructor | VRAM | Qué hace | Cómo |
|---|---|---|---|
| **TripoSR** | ~6 GB (con *fallback* a CPU) | 1 foto → malla en segundos, MIT | `git clone https://github.com/VAST-AI-Research/TripoSR` + `pip install -r requirements.txt` → pon la carpeta en `triposr_repo` |
| **Hunyuan3D-2GP** | 6 GB (con *offloading*) | 1 foto → malla, más calidad | repo `Hunyuan3D-2GP`, pon la carpeta en `hunyuan_repo` |
| **ComfyUI** + workflow 3D | según nodos | lo que tengas montado | deja ComfyUI corriendo; exporta el workflow a JSON y ponlo en `comfyui_workflow` |
| **Meshroom** | — (usa CPU/GPU) | vídeo o varias fotos → escaneo real (fotogrametría) | descarga Meshroom, pon `meshroom_batch` en `meshroom_bin` |

JARVIS prueba en este orden: TripoSR → Hunyuan3D → ComfyUI → Meshroom →
"imaginación".

## Formatos que acepta el holograma

`.blend .obj .fbx .stl .ply .dae .gltf .glb .x3d .abc .usd/.usdz/.usdc`
Blender headless los convierte a `.glb` y el visor los muestra.

## Uso por voz

- «modélame esto en 3D: C:\ruta\foto.jpg»
- «modela en 3D un dragón de jade» (texto)
- «modélame en 3D en T-pose: C:\ruta\personaje.fbx»
- «escanéame en 3D: C:\ruta\video.mp4» (fotogrametría si hay Meshroom)
- «muéstrame el holograma de eso» / «hazme el holograma pirámide de eso»

Salida en `%USERPROFILE%\Descargas\JARVIS\Modelos3D\<nombre>-<fecha>\`:
`modelo.glb/.obj/.stl`, `modelo_hero.png`, giro, `holograma.html` (se abre solo),
y `piramide_frames/` para la pirámide de acrílico sobre el móvil.

## Para el vídeo de giro/holograma como MP4

`pip install pillow imageio-ffmpeg` (si no, quedan los fotogramas sueltos).
