"""Subject resolution — CLI-SPEC §2, from a target string to a verifiable IR.

A verb operates on one subject, obtained one of three ways (§2.1) — a stored snapshot, a
serialized IR document, or a live object reached through an import — and this module is the
one place the three resolutions live. Detection (§2.2) is grammar over the target string in
a normative order; each resolver then fills the :class:`~gebra.verify.SubjectRef` the run
report's §1.3 rules fix for its mode. Every failure is a :class:`Refusal` carrying the
REPORT-FORMAT-SPEC §2.4 stage §2.6 maps it to: the verb turns one into a tool-error run
report, never into a traceback.

**The never-invokes boundary lives here** (§0.5, §2.4, WA-07). Import-path resolution is
exactly three steps: import the module (the user named it; its top-level code runs, as it
does for any Python import), read the attribute (nothing is called), and refuse anything
that is not already a workflow object — unless the invocation carried ``--call``, the one
path on which the CLI executes user code, once, with no arguments, and with **no signature
probe** (``__signature__``/``__wrapped__`` are user-influenced surfaces, so asking is
already running an inspection the user did not ask for). Everything after that is
``gebra.extract()``'s frozen read-only introspection, restated nowhere here.

:mod:`gebra.extraction` — and with it the substrate — is imported **inside** the
import-path resolver, never at module top. The laziness is load-bearing, exactly as it is
in ``gebra/__init__.py``: verifying an IR document or a stored snapshot reaches no
langgraph import at all, and ``tests/cli/test_never_invokes.py`` holds the whole
ir-document path to that in a guarded interpreter.
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, TypeAlias

from pydantic import ValidationError

if TYPE_CHECKING:
    # For annotations only: importing `gebra.extraction.warnings` at runtime would import
    # its parent package, and with it the substrate — exactly what the lazy boundary above
    # exists to keep off the ir-document and snapshot paths.
    from gebra.extraction.warnings import ExtractionWarning

from gebra.ir import (
    JSON_SUFFIXES,
    YAML_SUFFIXES,
    IRSerializationError,
    WorkflowIR,
    read_ir,
)
from gebra.report import did_you_mean, suggestion_sentence
from gebra.store import SnapshotStore, StoreError
from gebra.verify import SubjectRef

__all__ = [
    "IMPORT_REFERENCE_PATTERN",
    "VSFE_PATTERN",
    "Mode",
    "Refusal",
    "ResolvedSubject",
    "Stage",
    "detect_mode",
    "resolve_import_reference",
    "resolve_ir_document",
    "resolve_snapshot",
    "store_for",
]

#: §2.2 rule 1 — a V.S.F.E label: four dot-separated ASCII decimal components.
VSFE_PATTERN: Final = re.compile(r"^\d+\.\d+\.\d+\.\d+$")

#: §2.2 rule 3 — an import reference: ``module[.submodule…]:attribute``.
IMPORT_REFERENCE_PATTERN: Final = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$"
)

#: The three input modes, spelled as ``Subject.input_mode`` spells them (§2.1).
Mode: TypeAlias = Literal["snapshot", "ir-document", "extracted"]

#: The §2.4 stages a CLI resolution can stop at. ``dispatch`` is deliberately absent:
#: dispatch failures happen inside ``verify()``, which reports them itself.
Stage: TypeAlias = Literal["input", "extraction", "ir-validation"]


class Refusal(Exception):
    """A §2.6 resolution failure: no verdict was reached, and here is where it stopped.

    Attributes:
        stage: The REPORT-FORMAT-SPEC §2.4 stage — the vocabulary the diagnostic and the
            tool-error run report both use.
        detail: Display-only prose (§5.5): what was being resolved and what went wrong.
    """

    def __init__(self, stage: Stage, detail: str) -> None:
        super().__init__(detail)
        self.stage: Final[Stage] = stage
        self.detail: Final[str] = detail


@dataclass(frozen=True)
class ResolvedSubject:
    """One resolved subject: the IR to verify, its §1.3 provenance, and what riding it said.

    Attributes:
        ir: The workflow IR the validators read.
        reference: The caller-side half of the run report's ``subject`` (§1.3) —
            ``verify()`` composes it with the IR's own identity, which it computes rather
            than accepts.
        warnings: Extraction's structured warnings, in emission order — non-empty only in
            ``extracted`` mode. Rendered to stderr by the verb (§5.2), never dropped, and
            never a finding (§3.5).
    """

    ir: WorkflowIR
    reference: SubjectRef
    warnings: tuple[ExtractionWarning, ...] = ()


def detect_mode(target: str) -> Mode:
    """Which mode ``target``'s own grammar names — §2.2's detection, in its normative order.

    Rule 1 (V.S.F.E label) precedes rule 2 (IR suffix) because a label has no suffix; rule 2
    precedes rule 3 (import reference) because a Windows path can carry a colon while no
    import reference carries a recognized IR suffix. The order is normative and
    ``tests/cli/test_resolve.py`` tests it directly.

    Raises:
        Refusal: ``input`` — the target matches none of the three grammars. The detail
            names the shape the target came closest to (§2.2 rule 4).
    """
    if VSFE_PATTERN.match(target):
        return "snapshot"
    if Path(target).suffix.lower() in (*YAML_SUFFIXES, *JSON_SUFFIXES):
        return "ir-document"
    if IMPORT_REFERENCE_PATTERN.match(target):
        return "extracted"
    raise Refusal("input", _no_grammar_detail(target))


def _no_grammar_detail(target: str) -> str:
    """§2.2 rule 4's diagnostic: which of the three shapes ``target`` came closest to."""
    if re.fullmatch(r"[\d.]+", target):
        return (
            f"{target!r} names no subject: it is close to a V.S.F.E version label, but a "
            "label is exactly four dot-separated decimal components (e.g. 1.4.2.0)"
        )
    if ":" in target and "/" not in target and "\\" not in target:
        return (
            f"{target!r} names no subject: it is close to an import reference, but a "
            "reference is module[.submodule…]:attribute — dotted identifiers, one colon, "
            "one attribute name"
        )
    if "/" in target or "\\" in target or Path(target).suffix != "" or target.startswith("."):
        suffixes = ", ".join((*YAML_SUFFIXES, *JSON_SUFFIXES))
        return (
            f"{target!r} names no subject: it is close to an IR document path, but only "
            f"the suffixes {suffixes} name one — the suffix decides, and nothing sniffs "
            "content (CLI-SPEC §2.2)"
        )
    return (
        f"{target!r} names no subject. A target is one of three shapes (CLI-SPEC §2.2): a "
        "V.S.F.E version label (1.4.2.0), an IR document path (*.yaml, *.yml, *.json), or "
        "an import reference (package.module:attribute)"
    )


def resolve_ir_document(path_text: str) -> ResolvedSubject:
    """§2.1's ``ir-document`` mode: load the file at ``path_text`` with ``read_ir``.

    ``subject.source`` is the path exactly as the invocation gave it (§2.1), so a report is
    quotable back at the invocation that produced it.

    Raises:
        Refusal: ``input`` for a file that is missing, unreadable, of an unrecognized
            suffix, or not parseable as its format; ``ir-validation`` for a document that
            parses but does not satisfy the IR model (§2.6).
    """
    try:
        ir = read_ir(path_text)
    # UnicodeDecodeError first: it is a ValueError that is neither of the other two — the
    # file is not UTF-8 text, which §2.6 files under "unreadable", never under crash.
    except UnicodeDecodeError as error:
        raise Refusal(
            "input", f"{path_text!r} is not UTF-8 text, so it is no IR document: {error}"
        ) from error
    except IRSerializationError as error:
        raise Refusal("input", f"{path_text!r} is not a readable IR document: {error}") from error
    except ValidationError as error:
        raise Refusal(
            "ir-validation",
            f"{path_text!r} does not validate as an IR document: {error}",
        ) from error
    except OSError as error:
        raise Refusal("input", f"cannot read {path_text!r}: {error}") from error
    return ResolvedSubject(ir=ir, reference=SubjectRef(source=path_text, input_mode="ir-document"))


def store_for(store_dir: str | None) -> SnapshotStore:
    """The store an invocation names — ``--store DIR`` names the store directory **itself**.

    The default is ``./.gebra``, the store of the working directory's project, and there is
    no upward search (§2.5): an invocation that silently found a parent project's store
    would answer about a history the user was not looking at.
    """
    if store_dir is None:
        return SnapshotStore.for_project(Path.cwd())
    return SnapshotStore(store_dir)


def resolve_snapshot(label: str, store_dir: str | None) -> ResolvedSubject:
    """§2.1's ``snapshot`` mode: read the version ``label`` from the store.

    ``subject.source`` is the stored snapshot's ``extracted_from.source`` and
    ``subject.version`` the label (§2.1) — the stored digest itself is not taken on trust:
    the store re-checks it on read, and ``verify()`` recomputes the digest it reports.

    Raises:
        Refusal: ``input`` for a malformed label, a label the store does not hold (with
            §5.4's did-you-mean over the labels it does), or a store refusal — an
            unreadable index, a missing snapshot file, a failed digest check (§2.6).
    """
    if not VSFE_PATTERN.match(label):
        raise Refusal(
            "input",
            f"{label!r} is not a V.S.F.E version label: a label is four dot-separated "
            "decimal components, e.g. 1.4.2.0 (CLI-SPEC §2.2)",
        )
    store = store_for(store_dir)
    try:
        if not store.holds(label):
            raise Refusal("input", _unheld_label_detail(store, label))
        snapshot = store.read(label)
    except StoreError as error:
        raise Refusal("input", str(error)) from error
    return ResolvedSubject(
        ir=snapshot.ir,
        reference=SubjectRef(
            source=snapshot.extracted_from.source,
            input_mode="snapshot",
            version=snapshot.version,
        ),
    )


def _unheld_label_detail(store: SnapshotStore, label: str) -> str:
    """The unheld-version diagnostic, with §5.4's suggestion over the labels the store holds."""
    held = store.versions()
    if not held:
        return (
            f"the store at {store.path} holds no versions at all, so there is no "
            f"{label!r} to verify"
        )
    hint = suggestion_sentence(did_you_mean(label, held))
    return f"the store at {store.path} holds no version {label!r}" + (f". {hint}" if hint else "")


def resolve_import_reference(
    reference: str, *, call: bool = False, sidecar: str | None = None
) -> ResolvedSubject:
    """§2.1's ``extracted`` mode — §2.4's three steps, with its never-invokes boundary.

    Step one imports the named module (its top-level code runs — the user named it, and a
    definition that only exists after its module executes is reachable no other way). Step
    two reads the attribute; nothing is called. Step three hands a workflow object to
    ``extract()`` — and **refuses anything else** unless ``call`` is set, in which case the
    attribute is called exactly once, with no arguments and no signature probe, and the
    return value is the subject. The refusal is the default: without ``--call`` no
    attribute is ever called, so ``gebra verify pkg:main`` cannot start an application by
    accident.

    Raises:
        Refusal: ``input`` for everything up to and including obtaining the object — a
            reference outside the grammar, an import or attribute read that raised, a
            non-workflow attribute with no ``call``, a ``call`` that raised;
            ``extraction`` where ``extract()`` itself refused the object (§2.6).
    """
    if not IMPORT_REFERENCE_PATTERN.match(reference):
        raise Refusal(
            "input",
            f"{reference!r} is not an import reference: the shape is "
            "module[.submodule…]:attribute (CLI-SPEC §2.2)",
        )
    module_name, _, attribute_name = reference.partition(":")
    try:
        module = importlib.import_module(module_name)
    # SystemExit is not an Exception, and a module whose top level calls sys.exit() has
    # still just failed to import; anything above these two (KeyboardInterrupt, a test
    # sentinel) is deliberately left to §3.4's crash handling.
    except (Exception, SystemExit) as error:
        raise Refusal(
            "input",
            f"importing {module_name!r} raised {type(error).__name__}: {error}",
        ) from error
    try:
        attribute = getattr(module, attribute_name)
    except AttributeError as error:
        raise Refusal(
            "input",
            f"module {module_name!r} has no attribute {attribute_name!r}: {error}",
        ) from error
    except (Exception, SystemExit) as error:  # a module __getattr__ is the module's own code
        raise Refusal(
            "input",
            f"reading {attribute_name!r} from {module_name!r} raised "
            f"{type(error).__name__}: {error}",
        ) from error

    # The extractor — and with it the substrate — enters here and nowhere earlier.
    from gebra.extraction import ExtractionError, ExtractionErrorReason, classify, extract

    if call:
        try:
            workflow: object = attribute()
        except (Exception, SystemExit) as error:
            raise Refusal(
                "input",
                f"calling {reference!r} raised {type(error).__name__}: {error}. --call "
                "makes exactly one call, with no arguments (CLI-SPEC §2.4)",
            ) from error
    else:
        try:
            classify(attribute)
        except ExtractionError as error:
            if error.reason is ExtractionErrorReason.UNSUPPORTED_OBJECT:
                raise Refusal("input", _not_a_workflow_detail(reference, attribute)) from error
            # Any other reason means the attribute is workflow-shaped and extraction is
            # refusing it at its own boundary; extract() below states that refusal.
        workflow = attribute

    try:
        envelope = extract(workflow, sidecar=sidecar)
    except ExtractionError as error:
        raise Refusal("extraction", str(error)) from error
    return ResolvedSubject(
        ir=envelope.ir,
        reference=SubjectRef(
            source=reference,
            input_mode="extracted",
            extractor_version=envelope.extracted_from.extractor_version,
            sidecar=envelope.extracted_from.sidecar,
        ),
        warnings=envelope.warnings,
    )


def _not_a_workflow_detail(reference: str, attribute: object) -> str:
    """§2.4 step 3's refusal: what was found, and the two remedies, with nothing called."""
    from gebra.extraction import type_identity

    return (
        f"{reference} is {type_identity(attribute)}, not a workflow object (a "
        "StateGraph, a compiled graph, or another Runnable), and gebra did not call it "
        "(CLI-SPEC §2.4). Either name a module-level workflow object — `graph = "
        "build_graph()` in your own module makes construction part of the import — or "
        "pass --call to have gebra call this attribute once, with no arguments."
    )
