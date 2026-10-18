# Whisper English text normaliser: spelling table

`english.json` is OpenAI Whisper's British → American spelling table, used by the standard
Whisper English text normaliser (`EnglishTextNormalizer`). The normaliser code itself is the
copy shipped in Hugging Face transformers
(`transformers/models/whisper/english_normalizer.py`); this file is its only external input.

| | |
|---|---|
| Source | https://raw.githubusercontent.com/openai/whisper/ea1c266709125f68a89acdc0c6ddbde6773eb0ed/whisper/normalizers/english.json |
| Repository / path | openai/whisper, `whisper/normalizers/english.json` |
| Commit | `ea1c266709125f68a89acdc0c6ddbde6773eb0ed` (2023-01-18, the last change to this file) |
| Size | 56,128 bytes, 1,739 entries |
| Git blob SHA-1 | `74a1c3521d9af4a84a0aa65d95b0859138640799` (matches GitHub) |
| SHA-256 | `6607f948be9824d2e1b2fa2223cd94c06c45afa4e05ea0e3d5e1f2bdffde2465` |
| Licence | MIT, Copyright (c) 2022 OpenAI – see `LICENSE.openai-whisper` (same commit) |
| Downloaded | 2026-10-18, after approval (E0) |

`hub_speech_pipeline/asr/normalizer.py` checks the SHA-256 on load.
