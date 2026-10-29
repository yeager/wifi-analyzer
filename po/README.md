# Translations

WiFi Analyzer ships gettext catalogues for Arabic, German, Greek, British
English, Spanish, Finnish, French, Hindi, Italian, Japanese, Korean, Dutch,
Norwegian, Polish, Brazilian Portuguese, Russian, Swedish, Turkish, Ukrainian,
and Simplified Chinese.

Only completed and reviewed catalogues should be described as translations in
release notes. An empty catalogue deliberately falls back to the source text.

Update `po/wifi-analyzer.pot` whenever visible strings change, then merge it
into every locale with `msgmerge`. Validate all catalogues and build local
runtime files with:

```bash
python3 scripts/compile_translations.py
```

The build checks placeholders and format strings in every catalogue. It also
requires the Swedish catalogue to have no fuzzy or untranslated messages.
Other catalogues may be incomplete while they are being translated and will
fall back to the English source text.

Submit translation updates through GitHub pull requests. Generated `.mo` files
belong in build output and are not committed.
