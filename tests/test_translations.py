import gettext
from pathlib import Path
import subprocess
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


def test_swedish_channel_recommendation_explains_score_limits(tmp_path):
    compiled = tmp_path / "wifi-analyzer.mo"
    subprocess.run(
        [
            "msgfmt", "--check", "--check-format", "-o", str(compiled),
            str(ROOT / "po" / "sv.po"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    with compiled.open("rb") as catalogue_file:
        translated = gettext.GNUTranslations(catalogue_file)

    assert translated.gettext("Scan this band to compare nearby access points.") == (
        "Sök efter nätverk på det här bandet för att jämföra dem."
    )
    assert translated.gettext(
        "Lowest estimated overlap in this scan: channel {channel} (score {score})"
    ).format(channel=11, score=43.0) == (
        "Lägst beräknad överlappning i den här skanningen: kanal 11 (poäng 43.0)"
    )
    assert translated.gettext(
        "Lower scores mean less estimated overlap. The candidate is estimated at 20 MHz; reported access point widths are used when available. Only access points found in this scan count; client traffic and hidden networks are not measured."
    ) == (
        "Lägre poäng betyder mindre beräknad överlappning. Bedömningen räknar bara "
        "med 20 MHz för den föreslagna kanalen och använder rapporterad bredd för "
        "åtkomstpunkter när den finns. Den räknar bara nätverk som hittas vid "
        "skanningen och tar inte med trafik eller dolda nätverk."
    )


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
