# MCP Guide

## HTTP

Admin -> MCP:

- Transport: HTTP
- Endpoint: `https://example.com/mcp`

Test sends an `initialize` JSON-RPC request.

## STDIN/STDOUT

Admin -> MCP:

- Transport: STDIN/STDOUT
- Command: executable in the container
- Args: optional arguments

JARVIS writes one JSON-RPC line to STDIN and reads the final JSON response line from STDOUT.

## API Example

```bash
curl -X POST http://localhost:7860/api/mcp/http \
  -H "Authorization: Bearer <token>" \
  -H "X-CSRF-Token: <csrf>" \
  -H "Content-Type: application/json" \
  -d '{"server_id":1,"method":"initialize","params":{}}'
```
