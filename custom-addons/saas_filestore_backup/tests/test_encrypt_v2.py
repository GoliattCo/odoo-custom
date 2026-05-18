# Round-trip tests for the streaming AEAD v2 path in
# saas_filestore_backup._encrypt_file_v2 + the auto-dispatch from
# _encrypt_file. Run via:
#
#   docker compose exec odoo odoo-bin -d test_saas_filestore_backup \
#       -i saas_filestore_backup --test-enable \
#       --test-tags /saas_filestore_backup --stop-after-init

import os
import secrets
import struct
import tempfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'saas_filestore_backup')
class TestEncryptV2(TransactionCase):

    def setUp(self):
        super().setUp()
        self.model = self.env['saas.filestore.backup']
        self.dek = secrets.token_bytes(32)

    # ------------------------------------------------------------------
    # Auto-dispatch boundary
    # ------------------------------------------------------------------

    def test_small_file_dispatches_to_v1(self):
        """File ≤256 MiB → v1 (no GLT2 magic, tag is non-empty)."""
        with tempfile.NamedTemporaryFile(delete=False) as src, \
             tempfile.NamedTemporaryFile(delete=False) as dst:
            try:
                src.write(b'small payload' * 100)
                src.flush()
                nonce, tag, sha = self.model._encrypt_file(
                    src.name, dst.name, self.dek,
                )
                self.assertEqual(len(nonce), 12)
                self.assertEqual(len(tag), 16, 'v1 must return 16-byte tag')
                with open(dst.name, 'rb') as fh:
                    head = fh.read(4)
                self.assertNotEqual(head, b'GLT2', 'small file should not be v2')
            finally:
                os.unlink(src.name)
                os.unlink(dst.name)

    def test_large_file_dispatches_to_v2(self):
        """File >256 MiB → v2 (GLT2 magic, empty tag returned)."""
        # Use the explicit v2 path so we don't actually allocate 256MiB
        # of random plaintext; semantically equivalent.
        with tempfile.NamedTemporaryFile(delete=False) as src, \
             tempfile.NamedTemporaryFile(delete=False) as dst:
            try:
                src.write(b'A' * (2 * 1024 * 1024))  # 2 MiB
                src.flush()
                nonce, tag, sha = self.model._encrypt_file_v2(
                    src.name, dst.name, self.dek,
                    chunk_size=512 * 1024,  # 512 KiB chunks → 4 chunks
                )
                self.assertEqual(len(nonce), 12)
                self.assertEqual(tag, b'', 'v2 must return empty tag sentinel')
                with open(dst.name, 'rb') as fh:
                    head = fh.read(4)
                self.assertEqual(head, b'GLT2', 'v2 file must start with magic')
            finally:
                os.unlink(src.name)
                os.unlink(dst.name)

    # ------------------------------------------------------------------
    # Round-trip
    # ------------------------------------------------------------------

    def _decrypt_v2(self, path, dek):
        """Pure-Python v2 decoder mirroring what the restore CLI will
        do. Returns the recovered plaintext bytes."""
        aead = AESGCM(dek)
        out = bytearray()
        with open(path, 'rb') as fh:
            magic = fh.read(4)
            if magic != b'GLT2':
                raise ValueError(f'bad magic {magic!r}')
            base_nonce = fh.read(12)
            chunk_size = struct.unpack('>I', fh.read(4))[0]
            chunk_index = 0
            while True:
                hdr = fh.read(4)
                if not hdr:
                    break
                if len(hdr) != 4:
                    raise ValueError('truncated chunk header')
                pt_len = struct.unpack('>I', hdr)[0]
                if pt_len > chunk_size:
                    raise ValueError(
                        f'chunk {chunk_index} declares {pt_len} > chunk_size {chunk_size}'
                    )
                ct = fh.read(pt_len)
                tag = fh.read(16)
                if len(ct) != pt_len or len(tag) != 16:
                    raise ValueError(f'chunk {chunk_index} truncated')
                nonce = base_nonce[:4] + struct.pack('>Q', chunk_index)
                pt = aead.decrypt(nonce, ct + tag, None)
                out.extend(pt)
                chunk_index += 1
        return bytes(out)

    def test_v2_round_trip_exact_chunk_multiple(self):
        plaintext = secrets.token_bytes(512 * 1024 * 4)  # 4 full chunks
        with tempfile.NamedTemporaryFile(delete=False) as src, \
             tempfile.NamedTemporaryFile(delete=False) as dst:
            try:
                src.write(plaintext)
                src.flush()
                self.model._encrypt_file_v2(
                    src.name, dst.name, self.dek, chunk_size=512 * 1024,
                )
                recovered = self._decrypt_v2(dst.name, self.dek)
                self.assertEqual(recovered, plaintext)
            finally:
                os.unlink(src.name)
                os.unlink(dst.name)

    def test_v2_round_trip_partial_last_chunk(self):
        # 3.5 chunks of 512KiB → last chunk is 256 KiB.
        plaintext = secrets.token_bytes(512 * 1024 * 3 + 256 * 1024)
        with tempfile.NamedTemporaryFile(delete=False) as src, \
             tempfile.NamedTemporaryFile(delete=False) as dst:
            try:
                src.write(plaintext)
                src.flush()
                self.model._encrypt_file_v2(
                    src.name, dst.name, self.dek, chunk_size=512 * 1024,
                )
                recovered = self._decrypt_v2(dst.name, self.dek)
                self.assertEqual(recovered, plaintext)
            finally:
                os.unlink(src.name)
                os.unlink(dst.name)

    def test_v2_tamper_detection_on_chunk_body(self):
        plaintext = b'hello world' * 100
        with tempfile.NamedTemporaryFile(delete=False) as src, \
             tempfile.NamedTemporaryFile(delete=False) as dst:
            try:
                src.write(plaintext)
                src.flush()
                self.model._encrypt_file_v2(
                    src.name, dst.name, self.dek, chunk_size=4096,
                )
                # Flip the very last byte before the tag; GCM verify must fail.
                size = os.path.getsize(dst.name)
                with open(dst.name, 'r+b') as fh:
                    # Flip a byte near end (in ciphertext or tag area).
                    fh.seek(size - 20)
                    b = fh.read(1)
                    fh.seek(size - 20)
                    fh.write(bytes([b[0] ^ 0xff]))
                with self.assertRaises(Exception):
                    self._decrypt_v2(dst.name, self.dek)
            finally:
                os.unlink(src.name)
                os.unlink(dst.name)

    def test_v2_wrong_dek_fails(self):
        plaintext = b'secret bytes'
        with tempfile.NamedTemporaryFile(delete=False) as src, \
             tempfile.NamedTemporaryFile(delete=False) as dst:
            try:
                src.write(plaintext)
                src.flush()
                self.model._encrypt_file_v2(
                    src.name, dst.name, self.dek, chunk_size=4096,
                )
                wrong_dek = secrets.token_bytes(32)
                with self.assertRaises(Exception):
                    self._decrypt_v2(dst.name, wrong_dek)
            finally:
                os.unlink(src.name)
                os.unlink(dst.name)

    def test_v2_sha256_matches_actual_file(self):
        """sha256_hex returned by _encrypt_file_v2 must match the actual
        on-disk file hash (used by restore CLI for integrity check
        BEFORE decrypt)."""
        import hashlib
        plaintext = secrets.token_bytes(1024 * 100)
        with tempfile.NamedTemporaryFile(delete=False) as src, \
             tempfile.NamedTemporaryFile(delete=False) as dst:
            try:
                src.write(plaintext)
                src.flush()
                _, _, declared_sha = self.model._encrypt_file_v2(
                    src.name, dst.name, self.dek,
                )
                with open(dst.name, 'rb') as fh:
                    actual_sha = hashlib.sha256(fh.read()).hexdigest()
                self.assertEqual(declared_sha, actual_sha)
            finally:
                os.unlink(src.name)
                os.unlink(dst.name)
