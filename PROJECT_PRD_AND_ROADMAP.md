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

## 7. Current Status

### Completed

- Authentication and protected pages.
- Dashboard summary and status-balanced stock preview.
- Current stock management and pagination.
- Sales, customer returns, and supplier returns.
- Expiring stock page.
- Stock requirement page.
- Sales analytics page.
- Settings page with theme, preferences, FAQ, and support section.
- Interactive notifications.
- Medicines page with batch management.
- Archive, restore, and restricted permanent deletion.
- Dynamic administrator initials.
- Collapsible navigation sidebar.
- Compact page information cards across core pages.
- Dashboard View All link to paginated Current Stock.

### Validation Completed

- JavaScript syntax checks with `node --check`.
- Python syntax checks with `python -m py_compile`.
- VS Code diagnostics checked for changed files.
- Live medicine endpoint response verified during development.
- Git diff formatting checked for whitespace errors.

## 8. Immediate To-Do

### High Priority

- Add automated backend tests for archive, restore, delete, sale, and return safety rules.
- Add frontend interaction tests for sidebar, notifications, pagination, and medicine actions.
- Restart the FastAPI server in each environment after deployment so the `is_active` migration runs.
- Verify the PostgreSQL schema migration on a backup or staging database before production use.
- Add server-side validation for maximum field lengths and non-negative reorder levels.
- Replace the hard-coded session secret with an environment variable.
- Move the database URL and API base URL to environment configuration.

### Medium Priority

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

- Add `batch_id` to `SaleHistory` so each sale is linked to the exact batch.
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
