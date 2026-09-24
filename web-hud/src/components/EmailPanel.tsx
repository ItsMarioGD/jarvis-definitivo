import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mail, RefreshCw, Reply, Star, Eye, Send, ChevronLeft } from "lucide-react";
import { useHud, EmailMessage } from "../store/hudStore";
import { send } from "../hooks/useBridge";

export default function EmailPanel() {
  const emails = useHud((s) => s.emails);
  const setEmails = useHud((s) => s.setEmails);
  const loading = useHud((s) => s.emailsLoading);
  const setLoading = useHud((s) => s.setEmailsLoading);
  const markRead = useHud((s) => s.markEmailRead);

  const [selected, setSelected] = useState<EmailMessage | null>(null);
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);

  const fetchEmails = () => {
    setLoading(true);
    send({ type: "email/list" });
    // timeout fallback
    setTimeout(() => setLoading(false), 5000);
  };

  useEffect(() => {
    fetchEmails();
  }, []);

  // Listen for email data from bridge via chat messages tagged [EMAIL]
  useEffect(() => {
    const h = useHud.subscribe((state) => {
      const last = state.chat[state.chat.length - 1];
      if (last?.text?.startsWith("[EMAIL_DATA]")) {
        try {
          const data = JSON.parse(last.text.replace("[EMAIL_DATA]", ""));
          setEmails(data);
          setLoading(false);
        } catch {
          setLoading(false);
        }
      }
    });
    return h;
  }, []);

  const handleSelect = (e: EmailMessage) => {
    setSelected(e);
    markRead(e.id);
    send({ type: "email/read", id: e.id });
  };

  const handleReply = () => {
    if (!reply.trim() || !selected) return;
    setSending(true);
    send({ type: "chat", text: `responder al correo de ${selected.from} diciendo: ${reply}` });
    setTimeout(() => {
      setSending(false);
      setReply("");
    }, 2000);
  };

  const handleSummarize = () => {
    send({ type: "chat", text: "resume los correos no leídos" });
  };

  const unread = emails.filter((e) => !e.read).length;

  if (selected) {
    return (
      <div className="flex flex-col h-full">
        <div className="flex items-center gap-2 mb-3">
          <button
            onClick={() => setSelected(null)}
            className="p-1 rounded hover:bg-hud-cyan/10 text-hud-cyan_dim hover:text-hud-cyan transition-colors"
          >
            <ChevronLeft size={16} />
          </button>
          <span className="text-[10px] tracking-widest text-hud-cyan_dim flex-1 truncate">
            {selected.subject}
          </span>
          {selected.vip && <Star size={12} className="text-hud-warn shrink-0" />}
        </div>

        <div className="flex-1 overflow-y-auto mb-3">
          <div className="text-[11px] text-hud-cyan_dim mb-2">
            De: <span className="text-hud-ice">{selected.from}</span>
          </div>
          <div className="text-sm font-mono text-hud-ice/90 whitespace-pre-wrap leading-relaxed">
            {selected.body}
          </div>
        </div>

        <div className="border-t border-hud-cyan/10 pt-3">
          <textarea
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            placeholder="Escribe tu respuesta… o díselo a Jarvis por voz"
            className="w-full bg-hud-bg/60 border border-hud-cyan/20 rounded-lg
                       px-3 py-2 text-sm font-mono text-hud-ice resize-none
                       focus:outline-none focus:border-hud-cyan/50 min-h-[80px]"
          />
          <div className="flex gap-2 mt-2">
            <button
              onClick={handleReply}
              disabled={sending || !reply.trim()}
              className="flex items-center gap-2 px-4 py-2 rounded-lg
                         bg-hud-cyan/20 hover:bg-hud-cyan/30 text-hud-cyan
                         text-xs tracking-widest disabled:opacity-40
                         transition-colors"
            >
              <Send size={12} />
              {sending ? "ENVIANDO…" : "RESPONDER"}
            </button>
            <button
              onClick={() => send({ type: "chat", text: `responde al correo de ${selected.from} de forma profesional` })}
              className="flex items-center gap-2 px-3 py-2 rounded-lg
                         border border-hud-cyan/20 text-hud-cyan_dim
                         text-xs tracking-widest hover:border-hud-cyan/40
                         transition-colors"
            >
              <Reply size={12} />
              JARVIS
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 mb-3">
        <Mail size={14} className="text-hud-cyan text-glow-cyan" />
        <span className="text-[10px] tracking-[0.4em] uppercase text-hud-cyan_dim flex-1">
          Bandeja
        </span>
        {unread > 0 && (
          <span className="bg-hud-warn text-black text-[9px] font-bold px-2 py-0.5 rounded-full">
            {unread}
          </span>
        )}
        <button
          onClick={fetchEmails}
          disabled={loading}
          className="p-1 text-hud-cyan_dim hover:text-hud-cyan transition-colors"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
        <button
          onClick={handleSummarize}
          className="text-[9px] tracking-widest text-hud-cyan_dim hover:text-hud-cyan
                     transition-colors px-2 py-1 border border-hud-cyan/20 rounded"
        >
          RESUMIR
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-1">
        {loading && (
          <div className="text-center text-hud-cyan_dim text-[11px] py-8 tracking-widest animate-pulse">
            CARGANDO CORREOS…
          </div>
        )}
        {!loading && emails.length === 0 && (
          <div className="text-center text-hud-cyan_dim text-[11px] py-8">
            <Mail size={24} className="mx-auto mb-2 opacity-30" />
            <p className="tracking-widest">SIN CORREOS</p>
            <button
              onClick={() => send({ type: "chat", text: "lee mis correos nuevos" })}
              className="mt-3 text-hud-cyan text-[10px] border border-hud-cyan/20
                         px-3 py-1 rounded hover:bg-hud-cyan/10 transition-colors"
            >
              PEDIR A JARVIS
            </button>
          </div>
        )}
        <AnimatePresence>
          {emails.map((e) => (
            <motion.button
              key={e.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              onClick={() => handleSelect(e)}
              className={[
                "w-full text-left rounded-lg px-3 py-2 transition-colors",
                "border hover:border-hud-cyan/30",
                e.read
                  ? "bg-transparent border-hud-cyan/10 opacity-60"
                  : "bg-hud-cyan/5 border-hud-cyan/20",
              ].join(" ")}
            >
              <div className="flex items-start gap-2">
                {e.vip && <Star size={10} className="text-hud-warn shrink-0 mt-0.5" />}
                {!e.read && (
                  <span className="w-1.5 h-1.5 rounded-full bg-hud-cyan shrink-0 mt-1.5" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-[11px] font-mono text-hud-ice truncate">
                    {e.from}
                  </div>
                  <div className="text-[10px] text-hud-cyan_dim truncate">
                    {e.subject}
                  </div>
                </div>
              </div>
            </motion.button>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}
