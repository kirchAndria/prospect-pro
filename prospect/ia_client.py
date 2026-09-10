"""
Client IA unifié : Gemini avec fallback automatique vers Groq.
Gère retry, timeouts, errors gracefully et fournit des tests de connectivité.
"""
import re
import time
import logging
from prospect.config import (
    GEMINI_API_KEY, GROQ_API_KEY, GEMINI_MODEL, GROQ_MODEL,
    GROQ_MODELS_FALLBACK, get_logger
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
            json_mode: Forcer réponse JSON
            temperature: Créativité (0.0-1.0)

        Returns:
            Texte généré ou message d'erreur
        """
        # 1. Essai Gemini d'abord
        if self.gemini_client:
            result = self._call_gemini(
                prompt, max_retries=max_retries, json_mode=json_mode, temperature=temperature
            )
            if result:
                return result
            logger.warning("⚠️  Gemini échoué, bascule automatique vers Groq...")

        # 2. Fallback Groq
        if self.groq_client:
            result = self._call_groq(
                prompt, max_retries=max_retries, json_mode=json_mode, temperature=temperature
            )
            if result:
                return result
            logger.warning("⚠️  Groq aussi échoué")

        # 3. Dernier recours
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
                if resp and resp.text:
                    return resp.text.strip()

            except Exception as e:
                error_str = str(e).lower()

                # 503 = surcharge, retry
                if "503" in error_str or "overload" in error_str:
                    delay = 3 * (attempt + 1)
                    logger.warning(
                        f"⚠️  Gemini surcharge, retry {attempt + 1}/{max_retries} dans {delay}s..."
                    )
                    time.sleep(delay)
                    continue

                # Erreurs client ou quota ou 404
                if "401" in error_str or "404" in error_str or "quota" in error_str:
                    logger.error(f"❌ Gemini error ({e}) - bascule immédiate vers Groq")
                    return None

                logger.warning(f"⚠️  Gemini error (attempt {attempt + 1}): {e}")
                time.sleep(1)

        return None

    def _call_groq(
        self,
        prompt: str,
        max_retries: int = 2,
        json_mode: bool = False,
        temperature: float = 0.7,
    ) -> str | None:
        """Appelle Groq avec retry et fallback entre modèles Groq disponibles."""
        models_to_try = [GROQ_MODEL] + [m for m in GROQ_MODELS_FALLBACK if m != GROQ_MODEL]

        for model in models_to_try:
            for attempt in range(max_retries):
                try:
                    kwargs = {
                        "messages": [{"role": "user", "content": prompt}],
                        "model": model,
                        "temperature": temperature,
                        "max_tokens": 2000,
                    }
                    if json_mode:
                        kwargs["response_format"] = {"type": "json_object"}

                    message = self.groq_client.chat.completions.create(**kwargs)
                    raw_content = message.choices[0].message.content or ""
                    cleaned = self._clean_groq_content(raw_content)
                    if cleaned:
                        logger.info(f"✅ Réponse générée avec succès via Groq ({model})")
                        return cleaned

                except Exception as e:
                    error_str = str(e).lower()
                    if "rate_limit" in error_str or "429" in error_str:
                        delay = 3 * (attempt + 1)
                        logger.warning(f"⚠️  Groq {model} rate limited, retry dans {delay}s...")
                        time.sleep(delay)
                        continue

                    logger.warning(f"⚠️  Groq {model} error: {e}")
                    break

        return None

    def _clean_groq_content(self, text: str) -> str:
        """Nettoie le texte des éventuelles balises de raisonnement."""
        if not text:
            return ""
        cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
        return cleaned.strip()

    def _fallback_response(self, prompt: str) -> str:
        """Réponse de secours 100% locale."""
        if "json" in prompt.lower():
            return '{"error": "IA indisponible", "fallback": true}'
        return "⚠️  IA indisponible. Veuillez vérifier vos clés API."

    def test_gemini(self) -> tuple[bool, str]:
        """Teste la connexion à l'API Gemini."""
        if not self.gemini_client:
            return False, "Client Gemini non initialisé (clé manquante ou module absent)"
        try:
            resp = self.gemini_client.models.generate_content(
                model=GEMINI_MODEL,
                contents="Réponds uniquement par 'OK'."
            )
            text = (resp.text or "").strip()
            return True, f"Connecté ({GEMINI_MODEL}) : {text[:60]}"
        except Exception as e:
            return False, f"Erreur Gemini : {str(e)}"

    def test_groq(self) -> tuple[bool, str]:
        """Teste la connexion à l'API Groq."""
        if not self.groq_client:
            return False, "Client Groq non initialisé (clé manquante ou module absent)"
        try:
            message = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": "Réponds uniquement par 'OK'."}],
                model=GROQ_MODEL,
                max_tokens=50,
            )
            raw = message.choices[0].message.content or ""
            text = self._clean_groq_content(raw)
            return True, f"Connecté ({GROQ_MODEL}) : {text[:60]}"
        except Exception as e:
            return False, f"Erreur Groq : {str(e)}"


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
