import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Image as ImgIcon, Film, Music, X, Download } from "lucide-react";
import { useHud, type MediaItem } from "../store/hudStore";

function Tile({ item, onOpen }: { item: MediaItem; onOpen: () => void }) {
  const Icon = item.type === "video" ? Film : item.type === "audio" ? Music : ImgIcon;
  return (
    <button
      onClick={onOpen}
      className="group glass hud-corners relative rounded-md p-2 text-left w-full hover:bg-hud-cyan/10 transition"
    >
      <span className="c1" /><span className="c2" />
      <div className="aspect-video rounded bg-gradient-to-br from-hud-blue/30 to-hud-cyan/10 flex items-center justify-center mb-1">
        <Icon size={20} className="text-hud-cyan text-glow-cyan" />
      </div>
      <div className="text-[10px] text-hud-cyan_dim line-clamp-2">{item.prompt}</div>
      <div className="text-[9px] text-hud-cyan_dim/60 mt-0.5 font-mono">
        {new Date(item.ts).toLocaleTimeString("es-ES", { hour12: false })}
      </div>
    </button>
  );
}

export default function MediaViewer() {
  const media = useHud((s) => s.media);
  const [open, setOpen] = useState<MediaItem | null>(null);

  return (
    <>
      <div className="glass hud-corners relative rounded-lg p-3 w-full text-hud-ice">
        <span className="c1" /><span className="c2" />
        <div className="flex items-center gap-2 mb-2">
          <Film size={14} className="text-hud-cyan text-glow-cyan" />
          <span className="text-[10px] tracking-[0.4em] uppercase text-hud-cyan_dim">
            Multimedia Generada
          </span>
          <span className="ml-auto text-[10px] text-hud-cyan_dim font-mono">
            {media.length} ítems
          </span>
        </div>
        {media.length === 0 ? (
          <div className="text-hud-cyan_dim/50 italic text-xs py-3 text-center">
            Aún no se ha generado contenido. Pida a Jarvis un render o una ilustración.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2 max-h-64 overflow-y-auto pr-1">
            {media.slice(0, 12).map((m) => (
              <Tile key={m.id} item={m} onOpen={() => setOpen(m)} />
            ))}
          </div>
        )}
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-6"
            onClick={() => setOpen(null)}
          >
            <motion.div
              initial={{ scale: 0.92 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0.92 }}
              className="glass-strong rounded-xl p-4 max-w-3xl w-full text-hud-ice"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-3">
                <div className="font-mono text-xs text-hud-cyan_dim">{open.type.toUpperCase()}</div>
                <div className="flex items-center gap-2">
                  <a
                    href={open.path}
                    target="_blank"
                    rel="noreferrer"
                    className="p-1.5 rounded hover:bg-hud-cyan/20 text-hud-cyan"
                    title="Descargar"
                  >
                    <Download size={14} />
                  </a>
                  <button
                    onClick={() => setOpen(null)}
                    className="p-1.5 rounded hover:bg-hud-cyan/20 text-hud-cyan"
                  >
                    <X size={14} />
                  </button>
                </div>
              </div>
              <div className="aspect-video rounded bg-black/40 flex items-center justify-center">
                <ImgIcon size={48} className="text-hud-cyan text-glow-cyan" />
              </div>
              <div className="mt-3 text-sm">{open.prompt}</div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
