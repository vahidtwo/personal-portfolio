"""Encrypt users.sanjeh_token at rest ("enc1:" + Fernet, key = HKDF-SHA256(SECRET_KEY)).

Data-only: no column is added or changed (SQLite does not enforce VARCHAR length). Idempotent: rows that
already start with "enc1:" are skipped. Downgrade decrypts "enc1:" rows back to plaintext; a row that cannot
be decrypted with the current SECRET_KEY is left as it is and logged.

Revision ID: 0005_sanjeh_token_encrypt
Revises: 0004_sanjeh_status
"""
import logging

from alembic import op
from sqlalchemy import text

from app.token_crypto import PREFIX, decrypt_token, encrypt_token

revision = "0005_sanjeh_token_encrypt"
down_revision = "0004_sanjeh_status"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def _rows(conn):
    return conn.execute(text("SELECT id, sanjeh_token FROM users WHERE sanjeh_token IS NOT NULL AND sanjeh_token != ''")).fetchall()


def upgrade() -> None:
    conn = op.get_bind()
    for row_id, token in _rows(conn):
        if token.startswith(PREFIX):
            continue
        conn.execute(text("UPDATE users SET sanjeh_token = :t WHERE id = :i"), {"t": encrypt_token(token), "i": row_id})


def downgrade() -> None:
    conn = op.get_bind()
    for row_id, token in _rows(conn):
        if not token.startswith(PREFIX):
            continue
        plain = decrypt_token(token)
        if plain is None:
            logger.warning("users.id=%s: Sanjeh token cannot be decrypted with this SECRET_KEY; left encrypted", row_id)
            continue
        conn.execute(text("UPDATE users SET sanjeh_token = :t WHERE id = :i"), {"t": plain, "i": row_id})
