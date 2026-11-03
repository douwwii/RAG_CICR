"""Service d’embedding textuel et contrat de compatibilité, sans stockage."""
from collections.abc import Sequence
import hashlib
from importlib.metadata import version
import json
from typing import Literal, Protocol

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from config import EMBEDDING_CONFIG, EmbeddingConfig


class EmbeddingError(ValueError):
    """Configuration, entrée ou sortie d’embedding invalide."""


class EmbeddingCompatibilityError(EmbeddingError):
    """Le profil de l’index ne correspond pas au calcul demandé."""


class EmbeddingProfile(BaseModel):
    """Identité du calcul ; les paramètres de débit et de périphérique en sont exclus."""

    model_config = ConfigDict(strict=True, extra='forbid', frozen=True)

    schema_version: Literal[1]
    backend: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    revision: str = Field(pattern=r'^[0-9a-f]{40}$')
    dimension: int = Field(ge=1)
    normalize_embeddings: bool
    max_seq_length: int = Field(ge=1)
    query_prompt: str
    document_prompt: str
    precision: Literal['float32']
    backend_version: str = Field(min_length=1)
    transformers_version: str | None
    torch_version: str | None

    @property
    def fingerprint(self) -> str:
        serialized = json.dumps(self.model_dump(), sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


class EmbeddingService(Protocol):
    @property
    def dimension(self) -> int: ...

    @property
    def profile(self) -> EmbeddingProfile: ...

    def embed_documents(self, texts: Sequence[str]) -> NDArray[np.float32]: ...

    def embed_query(self, question: str) -> NDArray[np.float32]: ...


def ensure_embedding_compatible(stored: object, expected: EmbeddingProfile) -> None:
    """Refuse les profils absents, mal formés ou différents, même à dimension égale."""
    if stored is None:
        raise EmbeddingCompatibilityError('Profil d’embedding absent. Réindexation requise.')
    try:
        actual = EmbeddingProfile.model_validate(stored)
    except ValidationError as exc:
        raise EmbeddingCompatibilityError('Profil d’embedding invalide. Réindexation requise.') from exc
    differences = [
        key for key, value in expected.model_dump().items()
        if actual.model_dump()[key] != value
    ]
    if differences:
        raise EmbeddingCompatibilityError(
            f'Profils d’embedding incompatibles ({", ".join(differences)}). '
            'Utilisez une nouvelle collection et réindexez.'
        )


def _load_model(config: EmbeddingConfig):
    # Import différé : la configuration et les tests avec un encodeur fictif
    # restent utilisables sans importer Torch ni charger les poids.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        config.model_name,
        revision=config.revision,
        device=config.device,
        local_files_only=config.local_files_only,
        trust_remote_code=False,
    )


class SentenceTransformerEmbedder:
    def __init__(self, config: EmbeddingConfig = EMBEDDING_CONFIG):
        self._config = config
        try:
            self._model = _load_model(config)
        except Exception as exc:
            raise EmbeddingError(
                f'Chargement impossible de {config.model_name}@{config.revision[:12]} '
                f'(local_files_only={config.local_files_only}) : {exc}'
            ) from exc
        getter = getattr(self._model, 'get_embedding_dimension', None)
        if not callable(getter):
            getter = getattr(self._model, 'get_sentence_embedding_dimension', None)
        dimension = getter() if callable(getter) else None
        max_length = getattr(self._model, 'max_seq_length', None)
        if type(dimension) is not int or dimension < 1:
            raise EmbeddingError('Le modèle ne fournit pas de dimension entière positive.')
        if type(max_length) is not int or max_length < 1:
            raise EmbeddingError('Le modèle ne fournit pas de limite de tokens valide.')
        if not callable(getattr(self._model, 'tokenizer', None)):
            raise EmbeddingError('Un modèle textuel avec un tokenizer unique est requis.')
        self._profile = EmbeddingProfile(
            schema_version=1, backend='sentence-transformers', precision='float32',
            model_name=config.model_name, revision=config.revision,
            dimension=dimension, normalize_embeddings=config.normalize_embeddings,
            max_seq_length=max_length,
            query_prompt=self._resolve_prompt(config.query_prompt, ('query',)),
            document_prompt=self._resolve_prompt(config.document_prompt, ('document', 'passage', 'corpus')),
            backend_version=version('sentence-transformers'),
            transformers_version=version('transformers'), torch_version=version('torch'),
        )

    def _resolve_prompt(self, explicit: str | None, candidates: tuple[str, ...]) -> str:
        if explicit is not None:
            return explicit
        prompts = getattr(self._model, 'prompts', {})
        for name in candidates:
            if name in prompts:
                return prompts[name]
        default = getattr(self._model, 'default_prompt_name', None)
        return prompts[default] if default is not None else ''

    @property
    def profile(self) -> EmbeddingProfile:
        return self._profile

    @property
    def dimension(self) -> int:
        return self._profile.dimension

    def _check_texts(self, texts: Sequence[str], prompt: str) -> list[str]:
        if isinstance(texts, (str, bytes)) or not isinstance(texts, Sequence):
            raise EmbeddingError('Une séquence de textes est attendue.')
        texts = list(texts)
        for index, text in enumerate(texts):
            if not isinstance(text, str) or not text.strip():
                raise EmbeddingError(f'Texte [{index}] : une chaîne non vide est requise.')
        for start in range(0, len(texts), self._config.batch_size):
            # Compter les tokens sans troncature, instructions et tokens spéciaux compris.
            tokens = self._model.tokenizer(
                [prompt + text for text in texts[start:start + self._config.batch_size]],
                truncation=False, padding=False, add_special_tokens=True,
                return_attention_mask=False, return_token_type_ids=False,
                verbose=False,
            )['input_ids']
            for offset, token_ids in enumerate(tokens):
                if len(token_ids) > self.profile.max_seq_length:
                    raise EmbeddingError(
                        f'Texte [{start + offset}] : {len(token_ids)} tokens, '
                        f'limite {self.profile.max_seq_length}. '
                        'Découpez le texte avant le calcul des embeddings.'
                    )
        return texts

    def _validate_vectors(self, values: object, expected_shape: tuple[int, ...]) -> NDArray[np.float32]:
        try:
            vectors = np.asarray(values)
        except (TypeError, ValueError) as exc:
            raise EmbeddingError('Le modèle ne retourne pas un tableau numérique régulier.') from exc
        if vectors.shape != expected_shape:
            raise EmbeddingError(f'Forme des vecteurs invalide : {vectors.shape}, attendu {expected_shape}.')
        if vectors.dtype.kind != 'f':
            raise EmbeddingError('Le modèle doit retourner des vecteurs à virgule flottante.')
        with np.errstate(over='ignore', invalid='ignore'):
            vectors = vectors.astype(np.float32, copy=False)
        if not np.isfinite(vectors).all():
            raise EmbeddingError('Les vecteurs contiennent NaN ou des valeurs infinies.')
        norms = np.linalg.norm(vectors.astype(np.float64), axis=-1)
        if np.any(norms == 0):
            raise EmbeddingError('Le modèle a retourné un vecteur nul.')
        if self.profile.normalize_embeddings and not np.allclose(norms, 1.0, rtol=1e-5, atol=1e-6):
            raise EmbeddingError('Le modèle a retourné des vecteurs non normalisés.')
        return vectors

    def _encode_options(self, prompt: str) -> dict:
        return {
            'prompt': prompt, 'batch_size': self._config.batch_size,
            'normalize_embeddings': self.profile.normalize_embeddings,
            'precision': 'float32', 'convert_to_numpy': True,
            'convert_to_tensor': False, 'show_progress_bar': False,
        }

    def embed_documents(self, texts: Sequence[str]) -> NDArray[np.float32]:
        texts = self._check_texts(texts, self.profile.document_prompt)
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        vectors = self._model.encode_document(texts, **self._encode_options(self.profile.document_prompt))
        return self._validate_vectors(vectors, (len(texts), self.dimension))

    def embed_query(self, question: str) -> NDArray[np.float32]:
        self._check_texts([question], self.profile.query_prompt)
        vector = self._model.encode_query(question, **self._encode_options(self.profile.query_prompt))
        return self._validate_vectors(vector, (self.dimension,))
