"""Best-effort language metadata from redacted dossier prose."""
from functools import lru_cache

from langdetect import DetectorFactory, PROFILES_DIRECTORY
from langdetect.lang_detect_exception import LangDetectException


@lru_cache(maxsize=1)
def _factory() -> DetectorFactory:
    factory = DetectorFactory()
    factory.load_profile(PROFILES_DIRECTORY)
    factory.set_seed(0)
    return factory


def detect_language(text: str) -> tuple[str | None, float | None]:
    if sum(char.isalpha() for char in text) < 80:
        return None, None
    detector = _factory().create()
    detector.append(text)
    try:
        candidates = detector.get_probabilities()
    except LangDetectException:
        return None, None
    if not candidates or candidates[0].prob < 0.8:
        return None, None
    return candidates[0].lang, round(candidates[0].prob, 3)
