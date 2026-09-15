# SPDX-License-Identifier: MIT
"""Regression test: the Thin AppImage recipe must not re-introduce the
podman stack (0.6.0 item A, #357 / #363 root-cause fix).

Bundling rootless podman + helpers (conmon / crun / netavark /
aardvark-dns / pasta / passt / slirp4netns / fuse-overlayfs) is what
caused #357 (Ubuntu 26.04 -- bundled podman-compose shadowed the host's
working stack) and #363 (Fedora Bluefin -- bundled libcrypto poisoned
host systemd-run / aardvark-dns via LD_LIBRARY_PATH). The Thin redesign
drops the entire container stack from the AppImage; this test guards
against a future PR silently re-adding it.

The AppImage build is driven by:

* ``.github/workflows/appimage-publish.yml`` -- the CI workflow whose
  ``dnf install -y ...`` line is the package include list.
* ``packaging/appimage/bundle-system-bins.sh`` -- the BINARIES array
  that names the binaries copied out of the Fedora image into the
  AppDir.

Both files are scanned. If a forbidden token appears in either, fail
with a pointer back to this docstring so the author understands the
constraint before adding an opt-out.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "appimage-publish.yml"
BUNDLE_SCRIPT = REPO_ROOT / "packaging" / "appimage" / "bundle-system-bins.sh"

# Packages / binaries that must NOT be bundled into the Thin AppImage.
# Order: stack core, then helpers. Each is matched as a whole word so
# substrings (e.g. ``podman-compose`` containing ``podman``) don't
# false-positive each other.
FORBIDDEN_PACKAGES = (
    "podman",
    "podman-compose",
    "conmon",
    "crun",
    "netavark",
    "aardvark-dns",
    "passt",
    "pasta",
    "slirp4netns",
    "fuse-overlayfs",
)


def _read(path: Path) -> str:
    assert path.is_file(), f"expected file at {path}"
    return path.read_text(encoding="utf-8")


def _scan_dnf_install_block(workflow_text: str) -> str:
    """Return the ``dnf install -y ...`` argument block from the workflow.

    The workflow embeds the install line as part of a shell ``bash -c '...'``
    payload, with each package on its own line. We slice out everything
    between ``dnf install -y`` and the next ``echo`` line so a future
    rewording of the surrounding shell doesn't break the scan.
    """
    match = re.search(
        r"dnf\s+install\s+-y(?P<args>.*?)(?:^\s*echo\b|^\s*rpm\b|^\s*bash\b)",
        workflow_text,
        re.DOTALL | re.MULTILINE,
    )
    if match is None:
        # Workflow doesn't dnf install anything (CI re-architected) --
        # nothing to scan, the test passes vacuously on this file.
        return ""
    return match.group("args")


def _scan_bundle_binaries_array(script_text: str) -> str:
    """Return the BINARIES=( ... ) block contents from bundle-system-bins.sh."""
    match = re.search(
        r"BINARIES=\((?P<body>.*?)\)",
        script_text,
        re.DOTALL,
    )
    if match is None:
        return ""
    return match.group("body")


def _tokens(block: str) -> set[str]:
    """Split a whitespace-separated argument block into bare tokens.

    Ignores shell line-continuations, comments, and empty lines.
    """
    out: set[str] = set()
    for raw in block.splitlines():
        # Strip in-line comments after ``#``
        line = raw.split("#", 1)[0]
        # Drop the line-continuation backslash
        line = line.replace("\\", " ")
        for tok in line.split():
            out.add(tok)
    return out


def test_workflow_dnf_install_has_no_podman_stack_packages():
    text = _read(WORKFLOW)
    block = _scan_dnf_install_block(text)
    tokens = _tokens(block)
    found = sorted(tokens.intersection(FORBIDDEN_PACKAGES))
    assert not found, (
        "Thin AppImage regression: "
        f".github/workflows/appimage-publish.yml `dnf install -y` block reintroduced {found!r}. "
        "See tests/test_appimage_recipe.py docstring -- bundling rootless podman "
        "broke #357 and #363; 0.6.0 item A removed the stack."
    )


def test_bundle_script_binaries_array_has_no_podman_stack():
    text = _read(BUNDLE_SCRIPT)
    block = _scan_bundle_binaries_array(text)
    tokens = _tokens(block)
    found = sorted(tokens.intersection(FORBIDDEN_PACKAGES))
    assert not found, (
        "Thin AppImage regression: "
        f"packaging/appimage/bundle-system-bins.sh BINARIES=() reintroduced {found!r}. "
        "See tests/test_appimage_recipe.py docstring -- bundling rootless podman "
        "broke #357 and #363; 0.6.0 item A removed the stack."
    )


def test_workflow_does_not_pip_install_podman_compose():
    """podman-compose was pip-installed into the bundled interpreter
    (#322 workaround for ldd-bundling a pure-Python script). Thin drops
    that too -- the host's podman-compose is used directly."""
    text = _read(WORKFLOW)
    assert "pip install --no-cache-dir podman-compose" not in text, (
        "Thin AppImage regression: appimage-publish.yml re-introduced a "
        "`pip install podman-compose` into the bundled interpreter. The Thin "
        "AppImage requires host podman-compose; see tests/test_appimage_recipe.py."
    )
    assert "-m podman_compose" not in text, (
        "Thin AppImage regression: appimage-publish.yml re-introduced a "
        "podman-compose wrapper that runs ``python3 -m podman_compose``."
    )


def test_forbidden_tokens_are_known():
    """Lock the forbidden list so a future expansion is deliberate."""
    assert set(FORBIDDEN_PACKAGES) == {
        "podman",
        "podman-compose",
        "conmon",
        "crun",
        "netavark",
        "aardvark-dns",
        "passt",
        "pasta",
        "slirp4netns",
        "fuse-overlayfs",
    }


# --- Qt6 slimming guard -------------------------------------------------
# packaging/appimage/slim-pyside6.sh strips the Qt6 modules winpodx never
# imports from the bundled PySide6 (QtWebEngine etc. -- the bulk of the
# AppImage). If it ever drops a module the GUI actually uses, the AppImage
# build would produce a binary that crashes on launch. Cross-check the
# script's DROP_MODULES against the modules src/winpodx actually imports.

SLIM_SCRIPT = REPO_ROOT / "packaging" / "appimage" / "slim-pyside6.sh"
SRC_DIR = REPO_ROOT / "src" / "winpodx"


def _used_qt_modules() -> set[str]:
    """Qt module suffixes imported anywhere in src (e.g. {'Core','Widgets'})."""
    used: set[str] = set()
    pat = re.compile(r"from\s+PySide6\.Qt(\w+)\s+import|import\s+PySide6\.Qt(\w+)")
    for py in SRC_DIR.rglob("*.py"):
        for m in pat.finditer(py.read_text(encoding="utf-8")):
            used.add(m.group(1) or m.group(2))
    return used


def _drop_modules() -> set[str]:
    """Qt module suffixes listed in slim-pyside6.sh's DROP_MODULES array."""
    text = _read(SLIM_SCRIPT)
    m = re.search(r"DROP_MODULES=\((?P<body>.*?)\)", text, re.DOTALL)
    assert m is not None, "DROP_MODULES=( ... ) not found in slim-pyside6.sh"
    return _tokens(m.group("body"))


def test_slim_does_not_drop_a_qt_module_winpodx_uses():
    used = _used_qt_modules()
    # Sanity: the five modules we expect winpodx to use are present.
    assert {"Core", "Gui", "Widgets", "Svg", "DBus"} <= used, (
        f"unexpected Qt import set in src/winpodx: {sorted(used)} -- update the "
        "slim guard if the GUI legitimately gained/lost a Qt module."
    )
    clobbered = sorted(used & _drop_modules())
    assert not clobbered, (
        "slim-pyside6.sh DROP_MODULES would remove Qt module(s) winpodx imports: "
        f"{clobbered}. The AppImage GUI would crash on launch. Remove them from "
        "DROP_MODULES in packaging/appimage/slim-pyside6.sh."
    )


def test_slim_actually_drops_the_heavy_unused_modules():
    """Guard the win: the giant unused modules must stay on the droplist."""
    drop = _drop_modules()
    for heavy in ("WebEngineCore", "Quick", "Qml", "Multimedia", "Pdf", "Charts"):
        assert heavy in drop, (
            f"slim-pyside6.sh no longer drops {heavy!r} -- the AppImage will "
            "bloat back up. It's unused by winpodx; keep it on DROP_MODULES."
        )


# --- Zero-arg AppImage launch -> GUI ------------------------------------
# A double-clicked AppImage runs its AppRun with NO arguments. Today both
# AppRun templates forward "$@" straight to the CLI, so a bare launch prints
# `winpodx --help` to a terminal nobody sees. The approved behaviour maps the
# zero-argument case to the `gui` subcommand *immediately before* the existing
# exec, while leaving any explicit argument list untouched (so
# `./winpodx.AppImage setup` still runs `setup`). These tests read the AppRun
# text statically -- the AppImage is never built here -- and assert on the
# shell control flow strongly enough to tell a zero-arg launch apart from an
# explicit-arg passthrough.

# The CI-shipped AppRun template is a heredoc inside the publish workflow.
LOCAL_APPRUN = REPO_ROOT / "packaging" / "appimage" / "recipe" / "entrypoint.sh"
RECIPE_DESKTOP = REPO_ROOT / "packaging" / "appimage" / "recipe" / "winpodx.desktop"


def _workflow_apprun_body() -> str:
    """Return the AppRun heredoc body written by appimage-publish.yml.

    The workflow emits it via ``cat > AppDir/AppRun <<'APPRUN' ... APPRUN``.
    We slice between the heredoc open and its terminator so the assertions
    scan only the script that ends up executable in the AppImage.
    """
    text = _read(WORKFLOW)
    match = re.search(
        r"cat\s*>\s*AppDir/AppRun\s*<<'APPRUN'\n(?P<body>.*?)\n\s*APPRUN\b",
        text,
        re.DOTALL,
    )
    assert match is not None, "AppRun heredoc (<<'APPRUN' ... APPRUN) not found in workflow"
    return match.group("body")


def _maps_zero_args_to_gui_before_exec(body: str) -> bool:
    """True when the script injects ``gui`` for the zero-argument case and
    still forwards ``"$@"`` to the final exec.

    Distinguishes zero-arg from explicit-arg handling by requiring BOTH:

    * a shell test on the argument count being zero (``$#`` compared to 0),
      which is what makes the mapping apply only to a bare launch, appearing
      before the exec line; and
    * the exec still forwarding ``"$@"`` verbatim, which is what leaves an
      explicit argument list untouched.

    A template that unconditionally rewrote the args (breaking explicit
    passthrough) would fail the second half; one that never tests ``$#``
    (today's main) fails the first.
    """
    exec_match = re.search(r'^\s*exec\b.*"\$@".*$', body, re.MULTILINE)
    if exec_match is None:
        return False
    before_exec = body[: exec_match.start()]
    # ``$#`` compared against 0 in either order, e.g. `[ "$#" -eq 0 ]` or
    # `[ $# = 0 ]` or `(( $# == 0 ))`. The `gui` token must be the injected
    # default (``set -- gui`` is the POSIX-sh idiom).
    quoted_argc = r'["\']?\$#["\']?'
    quoted_zero = r'["\']?0["\']?'
    tests_zero_argc = re.search(
        rf"{quoted_argc}\s*(?:-eq|==|=)\s*{quoted_zero}"
        rf"|{quoted_zero}\s*(?:-eq|==|=)\s*{quoted_argc}",
        before_exec,
    )
    injects_gui = re.search(r"set\s+--\s+gui\b", before_exec)
    return bool(tests_zero_argc and injects_gui)


def test_workflow_apprun_maps_zero_args_to_gui_keeping_explicit_args():
    body = _workflow_apprun_body()
    # Sanity: the template still execs through the bundled interpreter with a
    # verbatim "$@" (explicit-arg passthrough is preserved).
    assert re.search(r'^\s*exec\b.*"\$@".*$', body, re.MULTILINE), (
        'appimage-publish.yml AppRun no longer forwards "$@"; explicit arguments would be dropped.'
    )
    assert _maps_zero_args_to_gui_before_exec(body), (
        "appimage-publish.yml AppRun does not map a zero-argument launch to "
        "the `gui` subcommand before its exec. A double-clicked AppImage "
        "prints CLI help instead of opening the GUI. Add a `$#`-is-zero guard "
        "that does `set -- gui` ahead of the existing "
        '`exec ... -m winpodx "$@"` line.'
    )


def test_local_recipe_entrypoint_maps_zero_args_to_gui_keeping_explicit_args():
    body = _read(LOCAL_APPRUN)
    assert re.search(r'^\s*exec\b.*"\$@".*$', body, re.MULTILINE), (
        'packaging/appimage/recipe/entrypoint.sh no longer forwards "$@"; '
        "explicit arguments would be dropped."
    )
    assert _maps_zero_args_to_gui_before_exec(body), (
        "packaging/appimage/recipe/entrypoint.sh does not map a zero-argument "
        "launch to the `gui` subcommand before its exec. A double-clicked "
        "local-build AppImage prints CLI help instead of opening the GUI. Add "
        "a `$#`-is-zero guard that does `set -- gui` ahead of the existing "
        '`exec "${PY_BIN_GLOB[0]}" "$@"` line.'
    )


def test_recipe_desktop_launches_the_gui_not_the_full_desktop():
    """The embedded .desktop must open the WinPodX GUI, not a full Windows
    desktop session. ``Exec=winpodx app run desktop`` boots a whole Windows
    desktop on a bare click; the approved target is ``winpodx gui``."""
    text = _read(RECIPE_DESKTOP)
    exec_line = next(
        (line for line in text.splitlines() if line.startswith("Exec=")),
        "",
    )
    assert exec_line == "Exec=winpodx gui", (
        "packaging/appimage/recipe/winpodx.desktop Exec is "
        f"{exec_line!r}; it must be 'Exec=winpodx gui' so a launched AppImage "
        "opens the WinPodX GUI rather than a full Windows desktop."
    )
