from jarvis_core import JarvisCore

def file_log(msg):
    with open("test_log.txt", "a", encoding="utf-8") as f:
        f.write(msg + "\n")

core = JarvisCore(log_callback=file_log)

file_log("Starting test...")
try:
    reply = core.process_text_stream("Hola Jarvis, di una sola oración.")
    file_log(f"FINAL REPLY: {reply}")
except Exception as e:
    file_log(f"EXCEPTION: {e}")
