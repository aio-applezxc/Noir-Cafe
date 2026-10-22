# Deployment templates

Apply only after following PLATFORM-SETUP.md. These files were prepared but have not been installed on your server.

Create a non-login `noir` Linux service account. Install the app into /opt/noir and its venv into /opt/noir/.venv. Give root ownership of application code, with the noir group allowed to read it. Keep .env readable only by root and noir (mode640); the application does not need write access to its source or .env. Install a working MySQL database and credentials first.

Copy noir.service to /etc/systemd/system/noir.service. Review it, then use `sudo systemctl daemon-reload` and `sudo systemctl enable --now noir`. Inspect `systemctl status noir` and `journalctl -u noir` for actual startup results.

Configure Nginx with a trusted internal certificate and the provided template; validate with `sudo nginx -t` before reloading Nginx. The browser connects to https://noir.cafe.test. Match internal DNS and TRUSTED_HOSTS to that hostname. Maintain certificate renewal/expiry monitoring.

The template deliberately does not forward client-controlled X-Forwarded-For into Flask or enable ProxyFix. Flask therefore rate-limits proxied logins by the proxy's IP as well as individual email; this is conservative but may throttle a busy café after repeated failures. If unique client IPs are needed, add a carefully trusted proxy configuration and tests before enabling it.

No Docker is required for the proposed Ubuntu VM design. Docker remains an optional local demo/test route in compose.yaml.
