# Translations

WiFi Analyzer ships gettext catalogues for Arabic, German, Greek, British
English, Spanish, Finnish, French, Hindi, Italian, Japanese, Korean, Dutch,
Norwegian, Polish, Brazilian Portuguese, Russian, Swedish, Turkish, Ukrainian,
and Simplified Chinese.

Update `po/wifi-analyzer.pot` whenever visible strings change, then merge it
into every locale with `msgmerge`. Validate all catalogues and build local
runtime files with:

```bash
python3 scripts/compile_translations.py
```

Submit translation updates through GitHub pull requests. Generated `.mo` files
belong in build output and are not committed.
