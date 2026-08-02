# Frontend Architecture & User Interface

The JARVIS frontend is a single-page React application built with Vite and vanilla CSS custom properties design tokens.

## Navigation & Page Modules

- **Admin Control Plane (`/admin`)**:
  - `Dashboard.jsx`: High-level metrics, pipeline phase banner, queue breakdown, and telemetry.
  - `Testing.jsx`: Command Center, diagnostic health runners, and Clear All Test Data maintenance action.
  - `Sources.jsx`: RSS feed URL management and validation.
  - `Models.jsx`: AI provider registration and task tier route priority tables.
  - `Users.jsx`: Administrator and user account management.
  - `Mcp.jsx`: Model Context Protocol transport configuration.
  - `Logs.jsx`: Real-time system log filter and search.
- **User Intelligence Console (`/user`)**:
  - `Feed.jsx`: Intelligence feed with severity filters (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
  - `Reports.jsx`: Executive daily summaries and Markdown / JSON exports.
  - `Assistant.jsx`: Interactive AI intelligence assistant.
  - `Preferences.jsx`: Personal notification settings.
