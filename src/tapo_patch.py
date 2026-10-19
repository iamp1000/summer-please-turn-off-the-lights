"""
Tapo Library Resilience Patch.

Fixes upstream plugp100 issues:
1. Strict UTF-8 decoding in TpapProtocol._load_json_dict crashes with UnicodeDecodeError
   when device returns raw or Latin-1 characters in effect IDs / strings (e.g. byte 0xBE
   in L930 DynamicZones effect ID).
2. Strict UTF-8 decoding in KlapChiper.decrypt crashes if session data contains non-UTF-8.
Applying robust latin-1 fallback prevents false HostUnreachableError and connection failures.
"""
import json
import logging
from typing import Any

log = logging.getLogger("TapoPatch")

def apply_tapo_patches() -> None:
    # 1. Patch TPAP protocol
    try:
        from plugp100.api.protocol.tpap.protocol import TpapProtocol
        from plugp100.api.transport.exceptions import TapoProtocolError

        if not getattr(TpapProtocol, "_is_robust_patched", False):
            def _robust_load_json_dict(payload: bytes) -> dict[str, Any]:
                try:
                    text = payload.decode("utf-8")
                except UnicodeDecodeError:
                    text = payload.decode("latin-1")
                response_data = json.loads(text)
                if not isinstance(response_data, dict):
                    raise TapoProtocolError("Unexpected TPAP JSON response body type")
                return response_data

            TpapProtocol._load_json_dict = staticmethod(_robust_load_json_dict)
            TpapProtocol._is_robust_patched = True
            log.debug("Applied robust JSON decode patch to TpapProtocol")
    except Exception as e:
        log.warning(f"Could not patch TpapProtocol: {e}")

    # 2. Patch KLAP protocol cipher
    try:
        from plugp100.api.protocol.klap.klap_protocol import KlapChiper
        from cryptography.hazmat.primitives.ciphers import Cipher, modes
        from cryptography.hazmat.primitives import padding

        if not getattr(KlapChiper, "_is_robust_patched", False):
            def _robust_klap_decrypt(self, msg: bytes) -> str:
                cipher = Cipher(self._aes_chiper, modes.CBC(self._cbc()))
                decryptor = cipher.decryptor()
                dp = decryptor.update(msg[32:]) + decryptor.finalize()
                unpadder = padding.PKCS7(128).unpadder()
                plaintextbytes = unpadder.update(dp) + unpadder.finalize()
                try:
                    return plaintextbytes.decode("utf-8")
                except UnicodeDecodeError:
                    return plaintextbytes.decode("latin-1")

            KlapChiper.decrypt = _robust_klap_decrypt
            KlapChiper._is_robust_patched = True
            log.debug("Applied robust decrypt patch to KlapChiper")
    except Exception as e:
        log.warning(f"Could not patch KlapChiper: {e}")

# Apply immediately upon module import
apply_tapo_patches()
