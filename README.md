# SMARTSTEELPAZHAYANNUR

A Flask website and private admin system for SMARTSTEELPAZHAYANNUR welding and fabrication work.

## Features

- Dashboard with KPI cards and recent projects
- Customer management and project history
- Project creation, editing, deletion, and status tracking
- Category-based project views
- Multi-file media uploads for images and videos
- Gallery with filters and previews
- Public homepage with featured staircase photo
- SQLite database persistence
- Admin login with password hashing
- Database upload backup utility

## Project structure

- `app.py` — application logic and routes
- `config.py` — runtime configuration
- `database/` — SQLite files
- `instance/` — runtime/admin setup files and backups
- `uploads/` — uploaded project media
- `public/static/` — CSS, JavaScript, and images (served as Vercel public assets)
- `templates/` — Flask templates

## Quick start

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Run the app:
   ```bash
   python app.py
   ```
3. Open http://127.0.0.1:5000 on the computer running the app. The public portfolio does not require a login.

The administrator sign-in page is at `/admin/login`. Customer records, project editing, uploads, deletion, settings, and backups require administrator sign-in.

To publish photos or videos, the owner signs in at `/admin/login` and can use
**Upload Work Photos / Videos** beside **Apply Filters** on the projects page,
or tap **Owner: Upload Photos** on the public website. After signing in, choose
a work category such as Staircase Work or
Handrail Work, then select a project in that category, choose a stage such as
Before Work or Completed Work, and select multiple supported media files.
Added photos and videos show on the public project page and in the matching
gallery category. Create a project first if you have not added one yet.
Customers do not need to register or sign in; they can browse the public
projects and gallery. The
homepage uses the latest uploaded project photo as its featured project image.
To add portfolio inspiration or preference photos without creating a project
or entering any customer details, choose **Owner: Add Photos (No Customer
Details)**. Select the work category and photos; they appear in the public
gallery and can be deleted there while signed in.
Before you upload project photos, it displays a
clearly attributed staircase inspiration photo by
[Parrish Freeman on Unsplash](https://unsplash.com/photos/white-metal-staircase-on-gray-concrete-floor-icgLeBd1XuE)
and welding inspiration photo by
[Christopher Burns on Unsplash](https://unsplash.com/photos/man-using-welding-machine-Wiu3w-99tNg).

## Access from other devices on your Wi-Fi

Keep the app running on the host computer, then open
`http://<host-computer-LAN-IP>:5000` on another device connected to the same
network. Find the host computer's IPv4 address with `ipconfig`. Windows
Firewall may need to allow inbound TCP traffic on port 5000 for private
networks. Do not expose the Flask development server directly to the public
internet.

## Access over the internet

To let visitors access the public portfolio from anywhere, deploy the app to a
hosting provider. Running it on a local computer only makes it reachable on
that computer or its local network. Use a production WSGI server and HTTPS.
SQLite and uploaded files need persistent storage, as configured for Render
below; Vercel instead uses hosted PostgreSQL and Blob storage. Configure
`FLASK_SECRET_KEY` to a long random secret, and set `ADMIN_USERNAME` and
`ADMIN_PASSWORD` before the first start.

## Deploy to Render

This repository includes `render.yaml` for a Flask web service. In Render,
choose **New → Blueprint**, connect
[this GitHub repository](https://github.com/midlaj132/SMARTSTEELFABRICATION),
and apply the blueprint. Render will install `requirements.txt`, start the app
with Gunicorn, generate a secret session key, and ask you to enter
`ADMIN_PASSWORD`.

The blueprint mounts a persistent disk at `/var/data` for the SQLite database
and uploaded work. It uses Render's Starter web-service plan because persistent
disks are not available on the free web-service plan. Keep the disk mounted at
`/var/data`; otherwise files written by the app will not persist across deploys.
After the first deploy, open `/healthz`; it should return `{"status":"ok"}`.
Owner upload remains at `/admin/login`, with username `SMARTSTEEL`.

## Deploy to Vercel

The root `app.py` exposes the Flask `app` object, so Vercel can detect it as a
Python application when importing this GitHub repository. Vercel Functions
cannot retain local SQLite files or uploaded files between executions. For
Vercel, this app uses hosted PostgreSQL and Vercel Blob instead; set up both
before the first deployment:

1. In Vercel, import `midlaj132/SMARTSTEELFABRICATION` and leave the project
   root at `/`. `app.py` exports the supported Flask `app` entry point.
   Vercel installs `requirements.txt`; no custom build command or
   `vercel.json` is needed. Static assets are under `public/static/` and are
   requested at `/static/...`.
2. Create a PostgreSQL database using a Vercel Marketplace provider such as
   Neon. Add its pooled connection string to the Vercel project environment as
   `DATABASE_URL` (or `POSTGRES_URL`).
3. Create a **public** Vercel Blob store and connect it to this project for
   Production (and Preview/Development if you use those environments). A
   connected store supplies `BLOB_STORE_ID` and `VERCEL_OIDC_TOKEN`
   automatically. Alternatively, create a read-write token and set
   `BLOB_READ_WRITE_TOKEN`. Uploaded photos and videos are public portfolio
   media.
4. In **Settings → Environment Variables**, add these for Production (and
   Preview if needed):
   - `FLASK_SECRET_KEY` — a long random secret used to sign owner sessions.
   - `ADMIN_USERNAME` — `SMARTSTEEL`.
   - `ADMIN_PASSWORD` — the owner’s password.
   - `DATABASE_URL` — the PostgreSQL connection string from the provider.
   - Blob credentials — connect the store to the project to provide
     `BLOB_STORE_ID` and `VERCEL_OIDC_TOKEN`, or add `BLOB_READ_WRITE_TOKEN`.
5. Redeploy. The app creates its tables in PostgreSQL on startup. Do not add
   database files, uploads, or secret values to GitHub.

Keep `DATABASE_URL` pointed at the same PostgreSQL database that already holds
your live projects and customers. The app does not drop tables or migrate local
SQLite contents automatically. Before changing the database provider or
connection string, export a backup and arrange a migration; otherwise the site
may appear empty because it is connected to a different database.

If a deployment reports `500 FUNCTION_INVOCATION_FAILED`, open the failed
deployment's **Functions → Logs** in Vercel. Startup logs identify missing
environment-variable names or the failed initialization phase without logging
secret values or customer records. Confirm the variables above are enabled for
the same environment (Production, Preview, or Development) as the deployment,
then redeploy.

Vercel Functions accept request bodies up to 4.5 MB. To keep uploads below that
platform limit, this app limits uploads to 4 MB total on Vercel (the limit can
be lowered with `MAX_UPLOAD_SIZE_MB`; Vercel values above 4 are capped).

Set these environment variables in Vercel’s dashboard, not in committed files.
Changing the local SQLite database does not migrate its contents to PostgreSQL;
the current repository intentionally excludes that local database.

## Default admin setup

On the first run, the application creates a secure admin account automatically. The credentials are saved in `instance/admin_credentials.txt` and printed in the console. You can also set your own password with the environment variables `ADMIN_USERNAME` and `ADMIN_PASSWORD` before starting the app.

## Backups

Use the backup option in the Settings page to create a ZIP archive containing the SQLite database and uploaded media.
