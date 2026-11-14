# Style guide (authoring notes, not part of the book)

Rules every chapter follows. Keep this file out of SUMMARY.md.

## Voice
- English, written by a senior developer to a colleague. Direct, concrete, no filler.
- No emojis. No marketing tone. No "In this chapter we will explore". Start with the substance.
- Say what breaks and why. A rule without its reason is not included.
- Short paragraphs. Prefer a code block and one sentence over three sentences of description.
- Avoid stock phrases: "powerful", "seamless", "leverage", "robust", "delve", "it is important to note".

## Chapter shape
1. One-paragraph statement of what the chapter solves.
2. Core material, with runnable examples.
3. "Pitfalls" section with real failure modes.
4. "Versions" section only if behaviour differs between 16 and 20.
5. Optional "Try it" with a shell or psql command the reader can run.

## Code
- Every example is complete enough to run or clearly marked as a fragment.
- Model names come from the standard Odoo models, or from the neutral teaching module `library` (`library.book`, `library.loan`). Never from client projects.
- Names, XML IDs, and fields in standard Odoo are verified against the real source before use. Unverified names are marked in the writing notes, never published.
- Sensitive data: no company names, domains, credentials, IDs, or client data in any example.

## Versions
- Written for the newest verified version, with differences marked by a "Versions" hint:
  `{% hint style="info" %}` for notes, `{% hint style="danger" %}` for breaking changes.
- Odoo 20 content is added only after it can be checked; until then it is not stated.

## Formatting
- GitBook hints: info (context), warning (pitfall), danger (data loss or breaking change), success (recommended practice).
- Tabs only for per-version or per-OS variants.
- Headings: one H1 per page, H2 for sections, H3 sparingly.
- Commands that change data are always preceded by their read-only counterpart.
