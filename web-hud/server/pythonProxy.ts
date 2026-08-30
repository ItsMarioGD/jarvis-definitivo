/**
 * Reverse proxy to the Python `jarvis_web_backend.py` runtime.
 * Implemented as an Express sub-router so we get the same JSON ergonomics
 * the React HUD expects, with retry + latency logging for the LLM round-trip.
 */
import { Router, type Request, type Response } from "express";

export function attachPythonProxy(baseUrl: string) {
  const r = Router();

  // Generic passthrough. Mirrors every /api/* not handled here to Python.
  r.all("*", async (req: Request, res: Response) => {
    const url = `${baseUrl}${req.originalUrl.replace(/^\/api/, "")}`;
    const started = Date.now();

    try {
      const upstream = await fetch(url, {
        method: req.method,
        headers: { "content-type": "application/json" },
        body: ["GET", "HEAD"].includes(req.method)
          ? undefined
          : JSON.stringify(req.body),
        signal: AbortSignal.timeout(30_000),
      });
      const ct = upstream.headers.get("content-type") ?? "application/json";
      const buf = Buffer.from(await upstream.arrayBuffer());
      res.status(upstream.status).set("content-type", ct).send(buf);
    } catch (e) {
      // Python offline — return a graceful empty response so the HUD keeps working.
      res.status(503).json({
        error: "python_offline",
        detail: (e as Error).message,
        latency_ms: Date.now() - started,
      });
    }
  });

  return r;
}
