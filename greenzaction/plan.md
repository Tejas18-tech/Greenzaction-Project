# Greenzaction implementation plan

## Scope
Greenzaction is a full-stack sustainable-spending platform. It will ship with a React/Vite browser client and a Python Flask REST API. MongoDB is the application datastore, selected through `MONGODB_URI`; optional Gemini/Manus-compatible AI calls are isolated behind a service with a deterministic rule-based fallback.

## Architecture
- `frontend/`: Vite React app, route-aware dashboard shell, auth state, API client, charts, transaction forms, analytics, rewards, goals, GreenBot, profile and admin views.
- `backend/`: Flask app factory, JWT middleware, MongoDB repositories, carbon/scoring/reward services, AI recommendation service, chatbot intents, admin endpoints and CSV import.
- `shared/`: API contracts and seed/reference data that are safe to share between client and server.
- Root Dockerfile, `.env.example`, README, and route manifest support local development and deployment.

## Design
- **Design movement:** quiet eco-fintech editorial dashboard.
- **Core principles:** calm hierarchy, high-trust data surfaces, visible sustainability context, responsive density.
- **Color philosophy:** deep forest ink and emerald signal reliability and measurable positive action; warm off-white surfaces keep the product approachable rather than clinical.
- **Layout paradigm:** persistent navigation rail with a spacious asymmetric content canvas; key metrics are grouped as a narrative rather than a repetitive card grid.
- **Signature elements:** emerald score ring, carbon “pulse” line, and mono-spaced evidence labels for emission methodology.
- **Interaction philosophy:** every action confirms its effect on footprint, score, or rewards; destructive actions are explicit and reversible where possible.
- **Animation:** short ease-out rises for metric refreshes, subtle chart draw-in, no distracting looping motion.
- **Typography:** Inter for interface hierarchy and reading; JetBrains Mono for data values, category tags, methodology and technical metadata.
- **Brand essence:** a transparent sustainability companion for everyday spending; measured, optimistic, credible.
- **Brand voice:** direct and encouraging. Example: “Your spending has a footprint. Make the next one lighter.” / “Estimated, explained, and yours to improve.”
- **Wordmark:** lowercase `greenzaction` with a leaf-shaped counter in the “a” and a compact pulse-mark favicon.
- **Signature brand color:** `#16865B` emerald green.

## Build workflow
1. Create the Flask API, environment contract, domain services, seed data and REST routes.
2. Create the React/Vite client with shared styling, authenticated shell and all required screens.
3. Wire client requests to the API and add clear loading, empty, error and estimate-confidence states.
4. Add route manifest, docs, container configuration and demo mode that works without external API keys.
5. Run frontend build, Python compile/smoke checks and inspect the integrated flows; fix confirmed issues.

## Data and safety decisions
Carbon estimates use category-based activity proxies rather than pretending transaction amount is a physical measurement. Each calculation records factor source, method and confidence. User queries always filter by user ID, and admin actions are role-gated. External keys are never committed.
