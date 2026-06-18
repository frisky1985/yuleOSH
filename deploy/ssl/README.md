# SSL Certificates

Place SSL certificates here. Auto-managed by Certbot in production.

For self-signed certs (development only):

    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout deploy/ssl/privkey.pem \
      -out deploy/ssl/fullchain.pem \
      -subj "/CN=localhost"
