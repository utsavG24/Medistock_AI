# MediStock Product Requirements, Status, and Roadmap

## 1. Product Overview

MediStock is a pharmacy inventory management system for tracking medicines, stock batches, expiry dates, stock actions, replenishment needs, and transaction history.

The product is designed for pharmacy administrators who need a clear operational view of inventory without losing historical accuracy.

## 2. Product Goals

- Track medicine inventory batch by batch.
- Identify low-stock, expiring, expired, and healthy inventory quickly.
- Record sales, customer returns, and supplier returns.
- Preserve analytics and audit history.
- Provide safe medicine lifecycle management through archive and restricted deletion.
- Keep daily workflows simple, responsive, and easy to scan.

## 3. Current Application Areas

### Dashboard

- Displays active medicine, stock, low-stock, and expiry summary cards.
- Shows a balanced preview of stock statuses instead of displaying only expiry-ordered records.
- Dashboard stock preview rotates through low-stock, expiring, expired, healthy, and out-of-stock groups.
- Medicine names are alphabetized inside each status group.
- The View All action opens the paginated Current Stock page.
- Includes concise page guidance and live inventory notifications.

### Current Stock

- Displays batch-level inventory.
- Supports search, category filtering, expiry-date filtering, and sorting.
- Supports pagination.
- Supports selling stock, customer returns, and supplier returns/exchanges.
- Prevents selling expired stock.
- Supports adding a new medicine with its first batch.

### Expiring Stock

- Shows expiring and expired batches.
- Supports search, status filtering, sorting, and pagination.
- Separates expiring-soon records from expired records through status badges.

### Stock Requirement

- Shows medicines that need replenishment.
- Calculates suggested order quantity using stock levels, reorder levels, and recent sales.
- Displays urgency, estimated cost, average daily sales, and stock remaining.
- Supports search, category filtering, sorting, and pagination.

### Medicines

- Lists medicine profiles and their batches.
- Supports search, category filtering, active/archived filtering, sorting, and pagination.
- Allows adding batches to existing active medicines.
- Allows archiving and restoring medicines.
- Allows permanent deletion only for records with no stock or history.
- Preserves medicine and batch history when analytics or return records exist.

### Sales Analytics

- Displays total revenue, sales, customer returns, and supplier returns.
- Lists transaction history.
- Records and displays the batch linked to each new sale; older sales without a batch link remain available for historical reporting.
- Supports search, transaction-type filtering, date filtering, sorting, and pagination.
- Keeps archived medicines available in historical analytics.

### Settings

- Light and dark themes.
- Theme preference persistence using local storage.
- Compact table preference.
- Local notification preferences.
- Searchable FAQ section.
- About MediStock section.
- Support email copy action.
- Reset preferences action.
- FAQ guidance explaining archive versus permanent deletion.

### AI Assistant

- Conversational pharmacy assistant for inventory, sales, returns, expiries, and reorder questions.
- Uses the backend request pipeline with Gemini or Ollama selected through `AI_PROVIDER`; an optional fallback model is a second Gemini model, not cross-provider fallback.
- Supports voice input for natural-language queries.
- Retains recent chat context so follow-up questions can reference earlier answers.
- Provides operational guidance based on current medicine, batch, and stock data rather than static text alone.

## 4. Shared Platform Behavior

### Authentication

- Login and signup are handled through the FastAPI backend.
- Protected pages use an authentication guard.
- The administrator name is loaded from the authenticated session.
- The admin avatar displays the first letter of the administrator's name.
- Logout clears the server session and redirects to login.

### Navigation

- Shared sidebar navigation across protected pages.
- Sidebar can be collapsed and expanded.
- Sidebar state is persisted locally.
- Desktop and mobile layouts are supported.
- Dark mode includes the sidebar and navigation controls.

### Notifications

- Bell icon opens an interactive notification center.
- Notifications are generated from low-stock and expiry data.
- Supports individual read state and mark-all-read.
- Unread state is persisted locally.
- Supports outside-click and Escape-key dismissal.

## 5. Data and Safety Rules

### Inventory Rules

- A medicine may contain multiple inventory batches.
- Batch quantity must be positive when creating a batch.
- Expiry date must be later than manufacture date.
- Duplicate batch numbers are rejected for the same medicine.
- Expired stock cannot be sold.
- Sales cannot exceed available batch quantity.
- Supplier returns cannot exceed available batch quantity.

### Archive Rules

- Archive is the normal lifecycle action for discontinued or inactive medicines.
- A medicine must have zero remaining stock before it can be archived.
- Archived medicines remain in the database and analytics.
- Archived medicines are hidden from active stock, expiry, low-stock, and replenishment views.
- Archived medicines cannot receive sales, returns, or new batches.
- Archived medicines can be restored by an authenticated administrator.

### Delete Rules

- Permanent deletion is intended only for accidental, duplicate, or test records.
- A medicine with sales or return history cannot be deleted.
- A medicine with remaining stock cannot be deleted.
- A batch with remaining stock cannot be deleted.
- A batch with return history cannot be deleted.
- A batch belonging to a medicine with sales history is conservatively protected because the current sales schema does not identify the specific sold batch.
- Destructive medicine and batch actions require an authenticated admin session.

## 6. Technical Architecture

### Frontend

- Static HTML pages.
- Shared CSS in `frontend/css/style.css`.
- Page-specific CSS for Settings and Medicines.
- Shared JavaScript in `frontend/js/app.js`.
- Authentication behavior in `frontend/js/auth.js`.
- Local storage is used for theme, sidebar, notification-read state, and preferences.

### Backend

- FastAPI application in `backend/main.py`.
- SQLAlchemy models in `backend/models.py`.
- PostgreSQL database configuration in `backend/database.py`.
- Session-based authentication.
- CORS configured for local development origins.

### Database Entities

- `Medicine`
- `InventoryBatch`
- `SaleHistory`
- `Return`
- `Admin`

The Medicine model includes an `is_active` flag. Existing PostgreSQL databases receive the column through a startup migration using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

## 7. Current Status and Progress Report

### Completed

- Authentication and protected pages.
- Dashboard summary and status-balanced stock preview.
- Current stock management and pagination.
- Sales, customer returns, and supplier returns.
- Expiring stock page.
- Stock requirement page.
- Sales analytics page.
- AI assistant page with conversational querying, Gemini/Ollama support, and voice input.
- Settings page with theme, preferences, FAQ, and support section.
- Interactive notifications.
- Medicines page with batch management.
- Archive, restore, and restricted permanent deletion.
- Dynamic administrator initials.
- Collapsible navigation sidebar.
- Compact page information cards across core pages.
- Dashboard View All link to paginated Current Stock.

### Progress Summary

The core pharmacy inventory workflow is implemented, but a static backend review found API authorization, inventory-integrity, and deployment-hardening gaps that should be closed before production use. The product is in stabilization, but these findings mean the backend is not yet production-ready.

The AI assistant is now part of the product surface and works as a contextual query layer over medicine, stock, sales, returns, and replenishment data. This adds a valuable operational layer for pharmacists and admins but should still be treated as an active feature requiring validation against a real deployment environment and data quality checks.

### Validation Completed

- JavaScript syntax checks with `node --check`.
- Python syntax checks with `python -m py_compile`.
- VS Code diagnostics checked for changed files.
- Live medicine endpoint response verified during development.
- FastAPI startup smoke test of the dashboard sales-trend endpoint completed successfully.
- Git diff formatting checked for whitespace errors.

### Backend Review Findings (Static Review — 2026-10-02)

This review inspected the FastAPI route definitions, request models, SQLAlchemy models, database setup, AI request pipeline, and frontend API calls. It did not inspect `.env`, contact a live API, or execute database mutations. Findings are based on code and should be verified with regression tests before release.

| Priority | Finding | Evidence / impact |
|---|---|---|
| Critical | Authentication is not enforced consistently. Dashboard, stock, transaction, stock-requirement, sales, and return routes have no `require_admin` dependency. This exposes pharmacy data and allows unauthenticated stock and transaction changes. | `backend/main.py`: `/dashboard/*`, `/stock/*`, `/sales`, `/returns/*`, and `/transactions`. `/medicines` and `/ai/*` do require a session. |
| High | Public signup has no invitation or owner-approval gate, while the data models do not associate medicines, batches, sales, or returns with a pharmacy/admin. If public signup is enabled, a second account has no data boundary from the first. | Signup: `backend/main.py`; shared entities: `backend/models.py`. |
| High | Sale and return request quantities are plain integers without positive-value constraints. Negative values can reverse stock changes and create negative or otherwise invalid transaction history; supplier replacement quantity is also unconstrained. | Request models and stock mutations: `backend/main.py` (`SellRequest`, `CustomerReturnRequest`, `SupplierReturnRequest`, `/sales`, `/returns/*`). |
| High | Stock availability is read, checked, and then updated without row locking or an atomic conditional update. Concurrent sale/return requests can both pass stale checks and leave stock and transaction history inconsistent. | Sale and return handlers: `backend/main.py` (`sell_stock`, `customer_return`, `supplier_return`). |
| Medium | Archive does not check that remaining stock is zero, despite the product safety rule. Separately, AI insights counts and classifies batches without consistently filtering archived medicines, so archived stock can distort its results. | `backend/main.py` (`archive_medicine`, `get_ai_insights`). |
| Medium | The configured AI provider is selected exclusively: Gemini's optional fallback is another Gemini model, while Ollama failures return an error. There is no Gemini-to-Ollama or Ollama-to-Gemini fallback. AI inputs also lack field-size/history-shape bounds; Gemini receives selected pharmacy data outside this application, and Ollama requests can occupy a worker for up to 180 seconds. Context truncation may cut off the question appended after the data. | `backend/main.py` (`AskRequest`, `generate_with_ollama`, `ask_ai`). |
| Medium | If `DATABASE_URL` is missing, the backend silently selects a local SQLite file even in production. On an ephemeral deployment this can cause data loss or an unexpected empty database. | `backend/database.py` (`DATABASE_URL`, `DEFAULT_SQLITE_PATH`). |
| Medium | Several list/report endpoints load all matching records without pagination or result limits; request throttling is also absent for login, signup, and AI. This creates avoidable database, memory, and worker-exhaustion risk as usage/data grows. | Examples: `backend/main.py` (`get_medicines`, `get_transactions`, AI routes); no rate limiting found in reviewed backend. |
| Medium | Low-stock summaries use an inner join against medicine stock aggregates, so active medicines with no batch rows are omitted instead of appearing as zero-stock items. AI insights also aggregates archived inventory in some totals. | `backend/main.py` (`get_summary`, `get_low_stock`, `get_ai_insights`). |

**Release assessment:** Resolve the Critical and High findings, add regression tests for unauthorized requests, negative quantities, and concurrent stock operations, and verify production database configuration before deploying. The frontend currently omits `credentials: "include"` for some dashboard and stock fetches, so those calls must be updated as part of enforcing API authentication.

## 8. Immediate To-Do

### High Priority

- Enforce authenticated admin access on every pharmacy-data endpoint and finalize the intended signup/tenant-isolation model.
- Add positive quantity, non-negative reorder-level, numeric price, and maximum text-length constraints to request models and database schema.
- Make sale and return stock changes atomic under concurrent requests.
- Enforce the zero-stock archive rule and align AI insight calculations with active-medicine visibility.
- Add automated backend tests for archive, restore, delete, sale, and return safety rules.
- Add authentication, invalid-input, and concurrent inventory-operation regression tests.
- Add frontend interaction tests for sidebar, notifications, pagination, and medicine actions.
- Restart the FastAPI server in each environment after deployment so the `is_active` migration runs.
- Verify the PostgreSQL schema migration on a backup or staging database before production use.
- Require `DATABASE_URL` in production and move the frontend API base URL to environment configuration.

### Medium Priority

- Bound AI question/history payloads, configure provider timeouts and request throttling, decide whether true cross-provider fallback is required, and review what pharmacy data may be sent to hosted model providers.
- Add pagination and indexes for inventory, transaction, and analytics queries.
- Make Settings notification toggles actively control which alerts are generated.
- Add loading states and retry controls for API-backed pages.
- Improve API error handling for expired sessions and network failures.
- Add a confirmation dialog component instead of browser `confirm` and `alert` calls.
- Add explicit empty states for every filtered table.
- Add a proper database migration tool such as Alembic.
- Add audit logging for archive, restore, delete, sale, and return actions.

## 9. Recommended Future Additions

### Medicine Lifecycle

- Add an archived-at timestamp and archived-by administrator ID.
- Add archive reasons such as discontinued, recalled, duplicate, or temporarily unavailable.
- Add a dedicated archived history view.
- Add bulk archive and restore actions with safeguards.
- Add medicine editing for profile fields such as category, unit price, manufacturer, and reorder level.

### Analytics Integrity

- Preserve immutable transaction snapshots such as medicine name, batch number, and unit price at the time of sale.
- Add transaction correction workflows instead of deleting transactions.
- Add export to CSV or PDF.
- Add date-range reports and trend charts.

### Inventory Operations

- Add stock adjustment records for damaged, expired, lost, or manually corrected units.
- Add purchase and supplier receiving workflows.
- Add barcode or QR-code scanning.
- Add multi-batch stock allocation rules such as FEFO: first expiry, first out.
- Add reorder draft creation from stock requirement recommendations.

### Administration

- Add multiple admin accounts and role-based permissions.
- Add a profile settings section with username and password changes.
- Add an optional profile image only when multi-user administration is introduced.
- Add notification delivery preferences for email or in-app alerts.
- Add security activity history and session management.

### Experience and Reliability

- Add responsive browser testing at desktop, tablet, and mobile widths.
- Add accessibility checks for keyboard navigation, focus states, labels, and contrast.
- Add backend health checks and structured logging.
- Add deployment configuration for production CORS, secrets, database credentials, and HTTPS.
- Add backups and restore procedures for the PostgreSQL database.

## 10. Product Decisions

- Keep administrator initials instead of profile image upload for the current single-admin workflow.
- Use Archive as the normal medicine lifecycle action.
- Keep Delete as a restricted cleanup action.
- Preserve analytics and transaction history over convenience.
- Keep page information cards short so stat cards remain visually dominant.
- Keep the dashboard preview balanced while preserving the full Current Stock page for detailed pagination and filtering.

## 11. Definition of Done for the Next Release

- Archive and restore behavior has automated tests.
- Delete safeguards have automated tests for stock, sales, returns, and empty records.
- Settings notification toggles affect notification generation.
- Database configuration and session secrets come from environment variables.
- Existing PostgreSQL databases have been migrated successfully in staging.
- Core pages pass desktop and mobile accessibility checks.
- A backup and rollback procedure is documented.
