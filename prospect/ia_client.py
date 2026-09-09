"""
Client IA unifié : Gemini avec fallback automatique vers Groq.
Gère retry, timeouts, errors gracefully.
"""
import time
import logging
from prospect.config import (
    GEMINI_API_KEY, GROQ_API_KEY, GEMINI_MODEL, GROQ_MODEL,
    get_logger
)

logger = get_logger("ia_client")

# ============================================================
# GEMINI CLIENT
# ============================================================

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = bool(GEMINI_API_KEY)
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-genai non installé")

# ============================================================
# GROQ CLIENT (Fallback)
# ============================================================

try:
    from groq import Groq as GroqClient
    GROQ_AVAILABLE = bool(GROQ_API_KEY)
except ImportError:
    GROQ_AVAILABLE = False
    logger.warning("groq non installé")


# ============================================================
# UNIFIED IA CALLER
# ============================================================

class IAClient:
    """Client IA avec retry + fallback Gemini → Groq."""

    def __init__(self):
        self.gemini_client = None
        self.groq_client = None

        if GEMINI_AVAILABLE:
            try:
                self.gemini_client = genai.Client(api_key=GEMINI_API_KEY)
                logger.info("✅ Gemini disponible")
            except Exception as e:
                logger.warning(f"⚠️  Gemini init failed: {e}")

        if GROQ_AVAILABLE:
            try:
                self.groq_client = GroqClient(api_key=GROQ_API_KEY)
                logger.info("✅ Groq disponible (fallback)")
            except Exception as e:
                logger.warning(f"⚠️  Groq init failed: {e}")

        if not self.gemini_client and not self.groq_client:
            logger.error("❌ Aucun client IA disponible!")

    def generate(
        self,
        prompt: str,
        max_retries: int = 3,
        json_mode: bool = False,
        temperature: float = 0.7,
    ) -> str:
        """
        Appelle IA avec retry + fallback.

        Args:
            prompt: Le prompt à envoyer
            max_retries: Nombre d'essais avant fallback
            json_mode: Forcer réponse JSON (Gemini only)
            temperature: Créativité (0.0-1.0)

        Returns:
            Texte généré ou message d'erreur
        """

        # Essai Gemini d'abord
        if self.gemini_client:
            result = self._call_gemini(
                prompt, max_retries=max_retries, json_mode=json_mode, temperature=temperature
            )
            if result:
                return result
            logger.warning("⚠️  Gemini échoué, bascule vers Groq...")

        # Fallback Groq
        if self.groq_client:
            result = self._call_groq(prompt, max_retries=max_retries, temperature=temperature)
            if result:
                return result
            logger.warning("⚠️  Groq aussi échoué")

        # Dernier recours
        return self._fallback_response(prompt)

    def _call_gemini(
        self,
        prompt: str,
        max_retries: int = 3,
        json_mode: bool = False,
        temperature: float = 0.7,
    ) -> str | None:
        """Appelle Gemini avec retry."""
        for attempt in range(max_retries):
            try:
                config = types.GenerateContentConfig(temperature=temperature)
                if json_mode:
                    config.response_mime_type = "application/json"

                resp = self.gemini_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=config,
                )
                return resp.text

            except Exception as e:
                error_str = str(e).lower()

                # 503 = surcharge, retry
                if "503" in error_str or "overload" in error_str:
                    delay = 5 * (attempt + 1)
                    logger.warning(
                        f"⚠️  Gemini surcharge, retry {attempt + 1}/{max_retries} "
                        f"dans {delay}s..."
                    )
                    time.sleep(delay)
                    continue

                # Erreur client = ne pas retry
                if "401" in error_str or "invalid" in error_str:
                    logger.error(f"❌ Gemini auth/quota error: {e}")
                    return None

                # Autres = log et continue
                logger.warning(f"⚠️  Gemini error (attempt {attempt + 1}): {e}")
                time.sleep(2)

        return None

    def _call_groq(
        self, prompt: str, max_retries: int = 3, temperature: float = 0.7
    ) -> str | None:
        """Appelle Groq avec retry."""
        for attempt in range(max_retries):
            try:
                message = self.groq_client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=GROQ_MODEL,
                    temperature=temperature,
                    max_tokens=2000,
                )
                return message.choices[0].message.content

            except Exception as e:
                error_str = str(e).lower()

                if "rate_limit" in error_str or "429" in error_str:
                    delay = 5 * (attempt + 1)
                    logger.warning(f"⚠️  Groq rate limited, retry dans {delay}s...")
                    time.sleep(delay)
                    continue

                logger.warning(f"⚠️  Groq error (attempt {attempt + 1}): {e}")
                time.sleep(1)

        return None

    def _fallback_response(self, prompt: str) -> str:
        """Réponse de secours 100% locale."""
        if "json" in prompt.lower():
            return '{"error": "IA indisponible", "fallback": true}'
        return "⚠️  IA indisponible. Réessayez plus tard."


# ============================================================
# SINGLETON GLOBAL
# ============================================================

_ia_client = None


def get_ia_client() -> IAClient:
    """Retourne le client IA singleton."""
    global _ia_client
    if _ia_client is None:
        _ia_client = IAClient()
    return _ia_client
