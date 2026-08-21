"""The deterministic emitter for the two `.gebra/` documents — PD-012's emitter rules.

D-11 In-Scope 1 asks for "deterministic serialization (stable key order, canonical emitter)
so snapshots diff cleanly under plain ``git diff``". PD-012 fixed which conventions that
means, and the answer was: **the ones the package already has.**

* **Key order is model declaration order**, never alphabetized — the envelope reads
  ``version``, ``extracted_from``, ``graph_version``, ``ir``, and the IR inside keeps
  ``WorkflowIR``'s own order. Explicitly *not* JCS/UTF-16 member order (PD-012 Option C,
  rejected): nothing reads a snapshot file expecting canonical order, since the digest is
  computed from the parsed model and never from these bytes (IR-SPEC §6.1 step 1), and a
  second "canonical-looking" surface form for the same content is one more thing to keep in
  sync with :func:`gebra.ir.serialization.dump_yaml` for no consumer's benefit.
* **Block style, ``allow_unicode=True``, UTF-8, LF, exactly one trailing newline** — again
  the choices IR-04's writer already makes, for the git-diff reason D-11 states directly.
* **Optional members holding ``None`` are omitted**, so absence round-trips to absence rather
  than to ``null`` (A6 PC-4). An empty store's ``meta.yaml`` carries no ``current`` line
  rather than ``current: null``.

**Determinism means: same document object in, same bytes out.** That is the claim PD-012
finding 6 spells out and the one this module can actually keep. It is *not* a claim that two
extractions of unchanged source produce identical files — an ``extracted_at`` moves between
them by design — and whether a re-snapshot of unchanged content is written at all is
:mod:`gebra.snapshot`'s policy, not this layer's. Nothing here reads a clock, iterates a ``set``, or depends on
``PYTHONHASHSEED``; ``tests/store/test_serialization.py`` checks that in four child
interpreters under four seeds rather than by assertion.

**One surface path, not two.** The document this module emits is an envelope of validated
scalars wrapped around a core IR, and the core IR is the part with foreign content in it
(``annotations.args_schema`` is ``dict[str, Any]``, carried verbatim). Everything that makes
reading and writing that content safe — a non-string mapping key refused rather than coerced,
a YAML timestamp or binary scalar refused, NaN/Infinity refused, a recursive anchor named
instead of overflowing the stack, an alias-expansion budget, and the string-quoting
correction for the four characters PyYAML would otherwise write unquoted and read back as
line breaks — already exists once, in :mod:`gebra.ir.serialization`. This module reaches it
by its module-private names rather than growing a second copy: a second copy of a guard is a
second place for it to drift, and these are guards where drift is silent. The names are
package-internal machinery on both sides of the seam, not a surface either module promises to
anyone outside :mod:`gebra`.

Errors are :class:`~gebra.ir.serialization.IRSerializationError` (the surface could not be
crossed) and pydantic's ``ValidationError`` (it was crossed and the document is not a store
document) — the same two-way split the IR surface draws, and
:class:`~gebra.store.store.SnapshotStore` is what turns either into a coded
:class:`~gebra.store.store.StoreError` naming the file.

Nothing in this module imports langgraph, opens a socket, or executes anything (WA-07).
"""

from __future__ import annotations

import json
from typing import Any, TypeVar, cast

# The four module-private names are the seam the module docstring explains: one surface
# path for the whole package, not a second copy of its guards.
from gebra.ir.serialization import (
    IRSerializationError,
    IRSerializationErrorReason,
    _Budget,
    _json_ready,
    _surface_dumper,
    _surface_loader,
    dump_json,
)
from gebra.store.base import StoreModel
from gebra.store.models import Snapshot, StoreMeta

__all__ = ["dump_meta", "dump_snapshot", "load_meta", "load_snapshot"]

_StoreModelT = TypeVar("_StoreModelT", bound=StoreModel)


def dump_snapshot(snapshot: Snapshot) -> str:
    """Serialize ``snapshot`` as the YAML text of ``.gebra/snapshots/<version>.yaml``.

    Raises:
        IRSerializationError: if the nested IR carries content YAML or JSON cannot represent
            — a non-finite number, a non-string key or a non-JSON type inside
            ``args_schema``, a container that contains itself, a document past the expansion
            or depth ceilings.
        ImportError: if PyYAML is not installed.
    """
    document = _document(snapshot, exclude={"ir"})
    # Re-read what the IR surface writer produced, rather than dumping the nested model
    # again here: `dump_json` is the guarded path, and going through its text means the IR
    # subtree of a snapshot is byte-for-byte the document `gebra.ir.write_ir` would have
    # written on its own, one indent level down.
    document["ir"] = json.loads(dump_json(snapshot.ir, indent=None))
    return _dump_yaml(document)


def dump_meta(meta: StoreMeta) -> str:
    """Serialize ``meta`` as the YAML text of ``.gebra/meta.yaml``.

    Raises:
        ImportError: if PyYAML is not installed.
    """
    return _dump_yaml(_document(meta))


def load_snapshot(source: str | bytes) -> Snapshot:
    """Validate YAML text as a :class:`~gebra.store.models.Snapshot`.

    Raises:
        IRSerializationError: if the text is not well-formed YAML or carries what JSON has no
            form for (see :func:`gebra.ir.serialization.load_yaml` — this is the same path).
        pydantic.ValidationError: if the document is not a snapshot: a version label unusable
            as a file name, a digest outside the IR-SPEC §6.1 step-8 grammar, a timestamp in
            another spelling, an unknown member, or an IR that does not satisfy the §2 model.
        UnicodeDecodeError: (a ``ValueError``) if ``source`` is ``bytes`` that are not UTF-8.
        ImportError: if PyYAML is not installed.
    """
    return _load(Snapshot, source)


def load_meta(source: str | bytes) -> StoreMeta:
    """Validate YAML text as a :class:`~gebra.store.models.StoreMeta`.

    Raises:
        IRSerializationError: as for :func:`load_snapshot`.
        pydantic.ValidationError: if the document is not a store index — including the two
            history invariants, a repeated version and a ``current`` the history does not
            hold.
        UnicodeDecodeError: (a ``ValueError``) if ``source`` is ``bytes`` that are not UTF-8.
        ImportError: if PyYAML is not installed.
    """
    return _load(StoreMeta, source)


def _document(model: StoreModel, *, exclude: set[str] | None = None) -> dict[str, Any]:
    """``model`` as JSON data: declaration order, ``None``-valued members dropped.

    The round trip through JSON text is what normalizes the dump to exactly the built-in
    types the emitter admits — a ``tuple`` to a list, and a ``str`` subclass (which strict
    validation still admits, and which PyYAML's representer table looks up by exact type) to
    a ``str``. Every member of a store document is a validated scalar or a nested store
    model, so there is nothing here for the encoder to refuse; the IR subtree, which is the
    part that carries foreign content, goes through
    :func:`gebra.ir.serialization.dump_json` instead.
    """
    dumped = model.model_dump(mode="python", by_alias=True, exclude_none=True, exclude=exclude)
    return cast("dict[str, Any]", json.loads(json.dumps(dumped, ensure_ascii=False)))


def _dump_yaml(document: dict[str, Any]) -> str:
    """The PD-012 emitter: block style, declaration order, unicode as itself, one newline."""
    yaml = _yaml_module()
    dumped: str = yaml.dump(
        document,
        Dumper=_surface_dumper(),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    return dumped


def _load(model_type: type[_StoreModelT], source: str | bytes) -> _StoreModelT:
    """Parse, re-encode, validate — :mod:`gebra.ir.serialization`'s ingestion path.

    IR-SPEC §2.5 note 4 forces it on the IR models and the same force applies here: the store
    models are ``strict=True``, and under strict Python-mode validation a ``list`` is not a
    ``tuple``, so YAML data validates into ``history`` only in JSON mode.
    """
    yaml = _yaml_module()
    text = source.decode("utf-8") if isinstance(source, bytes) else source
    try:
        data = yaml.load(text.removeprefix("﻿"), _surface_loader())
    except yaml.YAMLError as exc:
        raise IRSerializationError(
            f"the document is not well-formed YAML: {exc}",
            reason=IRSerializationErrorReason.YAML_SYNTAX,
        ) from exc
    except RecursionError as exc:
        raise IRSerializationError(
            f"the document is nested too deeply to parse ({exc})",
            reason=IRSerializationErrorReason.TOO_COMPLEX,
        ) from exc
    ready = _json_ready(data, (), frozenset(), _Budget())
    return model_type.model_validate_json(json.dumps(ready, ensure_ascii=False))


def _yaml_module() -> Any:
    """PyYAML, imported on use — the same lazy import, and the same message, IR-04 uses.

    It is not a declared dependency of this package (it arrives with ``langchain-core``), so a
    stripped environment gets one actionable sentence at the call rather than an import error
    at ``import gebra``.
    """
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover — PyYAML is present in the dev environment
        raise ImportError(
            "reading or writing the .gebra/ store requires PyYAML, which is not installed; "
            "install it (`pip install PyYAML`)"
        ) from exc
    return yaml
