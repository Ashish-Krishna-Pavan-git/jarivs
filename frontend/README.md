# JARVIS Frontend

The JARVIS frontend is a single-page React application built with Vite. It provides two operational consoles:
1. **Admin Control Console (`/admin`)**: Dashboard, Command Center / Testing, Source Management, Model Routing, User Administration, Integrations/Channels, MCP Servers, Storage, Event Logs, System Health, Settings.
2. **User Intelligence Console (`/user`)**: Real-time Intelligence Feed, Executive Reports & Exports, Interactive AI Assistant, Personal Channels, and Preferences.

## Architecture

- **Build System**: Vite 6.x
- **Framework**: React 18+ (Pure JSX, functional components, hooks)
- **Styling**: Modern Vanilla CSS with CSS Custom Properties tokens ([`src/styles/app.css`](file:///C:/Users/Ashish%20Krishna%20Pavan/Desktop/JarvisD/Jarvis-Agent/frontend/src/styles/app.css)). Dark/Light theme switching.
- **Icons**: `lucide-react`
- **Navigation**: Zero-reload URL mode switching (`history.pushState`) + Hash-based sub-route navigation (`#dashboard`, `#testing`, `#feed`, `#reports`, etc.).

## Directory Structure

```text
frontend/
├── dist/                # Production build bundle output (served by Flask backend)
├── index.html           # HTML entrypoint
├── package.json         # Dependencies and build scripts
├── vite.config.js       # Vite configuration
└── src/
    ├── main.jsx         # Application root entry point
    ├── App.jsx          # Root router, mode switcher, and error boundary
    ├── api.js           # Centralized API fetch wrapper (JWT, CSRF, JSON error handling)
    ├── components/      # Shared components (Shell, Auth, UI primitives)
    │   ├── Auth.jsx     # Login and Password Change forms
    │   ├── Shell.jsx    # Sidebar navigation and header layout
    │   ├── Button.jsx   # Button primitive component
    │   └── ui.jsx       # Field, Metric, Header, and Table components
    ├── pages/           # Page view components
    │   ├── Channels.jsx # Shared channel notification configuration
    │   ├── JsonPage.jsx # General JSON inspector view component
    │   ├── admin/       # Administrator control plane views
    │   │   ├── Dashboard.jsx # Overview, phase banner, queue, AI status, telemetry
    │   │   ├── Testing.jsx   # Command Center & Diagnostics page
    │   │   ├── Sources.jsx   # Feed source management
    │   │   ├── Models.jsx    # Model provider & route configuration
    │   │   ├── Users.jsx     # User management
    │   │   ├── Mcp.jsx       # MCP server transport management
    │   │   └── Logs.jsx      # Live event log filter & search
    │   └── user/        # End-user intelligence views
    │       ├── Feed.jsx        # Intelligence feed with severity filters
    │       ├── Reports.jsx     # Executive reports & Markdown/JSON export
    │       ├── Assistant.jsx   # Interactive AI Q&A assistant
    │       └── Preferences.jsx # User preference storage
    └── styles/
        └── app.css      # Design system CSS rules, color tokens, layout
```

## Running Locally

To run the frontend dev server with hot module replacement:

```bash
cd frontend
npm install
npm run dev
```

To compile the production distribution bundle (`frontend/dist`):

```bash
cd frontend
npm run build
```

The compiled `dist/` directory is automatically served by Flask backend at `/`, `/admin`, and `/user`.
