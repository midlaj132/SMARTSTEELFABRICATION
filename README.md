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
- `static/` — CSS/JS assets
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
that computer or its local network. Use a production WSGI server, HTTPS, and a
persistent disk for the SQLite database and uploaded media. Configure
`FLASK_SECRET_KEY` to a long random secret, and set `ADMIN_USERNAME` and
`ADMIN_PASSWORD` before the first start.

## Default admin setup

On the first run, the application creates a secure admin account automatically. The credentials are saved in `instance/admin_credentials.txt` and printed in the console. You can also set your own password with the environment variables `ADMIN_USERNAME` and `ADMIN_PASSWORD` before starting the app.

## Backups

Use the backup option in the Settings page to create a ZIP archive containing the SQLite database and uploaded media.
