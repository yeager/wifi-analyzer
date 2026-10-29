from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from compile_translations import validate_project_id, validate_swedish_catalogue


HEADER = '''msgid ""
msgstr ""
"Project-Id-Version: wifi-analyzer\\n"
"Language: sv\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\\n"
'''


def test_current_swedish_catalogue_is_complete():
    validate_swedish_catalogue(ROOT / "po" / "sv.po")


@pytest.mark.parametrize("project_id", ["", "PACKAGE VERSION"])
def test_default_project_id_is_rejected(tmp_path, project_id):
    catalogue = tmp_path / "translation.po"
    catalogue.write_text(
        f'msgid ""\nmsgstr ""\n"Project-Id-Version: {project_id}\\n"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Project-Id-Version"):
        validate_project_id(catalogue)


def test_current_catalogues_have_project_id():
    for catalogue in sorted((ROOT / "po").glob("*.po")):
        validate_project_id(catalogue)


@pytest.mark.parametrize(
    "entry",
    [
        'msgid "Hello"\nmsgstr ""\n',
        '#, fuzzy\nmsgid "Hello"\nmsgstr "Hej"\n',
        'msgid "Hello"\nmsgstr "Hej"\n',
    ],
    ids=["untranslated", "fuzzy", "missing-template-entries"],
)
def test_incomplete_swedish_catalogue_is_rejected(tmp_path, entry):
    catalogue = tmp_path / "sv.po"
    catalogue.write_text(HEADER + "\n" + entry, encoding="utf-8")

    with pytest.raises(ValueError, match="Swedish catalogue"):
        validate_swedish_catalogue(catalogue)
