# Writing guide for contributors

This file is not part of the book and is not listed in `SUMMARY.md`.

## Text

- Write in plain English, in the second person where it helps. Give the rule and the reason for it.
- Start a chapter with the problem it solves. Skip introductions about what the chapter will cover.
- Keep paragraphs short. A code block and one sentence beat three sentences of description.
- Say what breaks and why. A rule with no reason does not belong.
- Use concrete numbers and names instead of adjectives.

## Chapter layout

1. The problem the chapter solves, in a short paragraph.
2. The material, with examples that run or are marked as fragments.
3. A "Pitfalls" section with failures that actually happen.
4. A "Versions" section only where Odoo 16 to 20 differ.
5. Optional "Try it" exercises with solutions in `<details>`.

## Code

- Examples are complete enough to run, or clearly marked as fragments.
- Models come from standard Odoo or from the teaching module `library` (`library.book`, `library.loan`). Do not use names from real projects.
- Check every standard name (model, field, XML id, method signature) in the Odoo source before using it. State the version you checked.
- No company names, domains, credentials, ids or client data in examples.
- A command that changes data comes after the read-only command that shows what it will change.

## Versions

- Write for Odoo 18 and mark differences for 16, 17 and 20 in a version note.
- Use `{% hint style="info" %}` for notes and `{% hint style="danger" %}` for breaking changes.
- If a point could not be checked in a version, say so instead of guessing.

## Formatting

- Hints: info for context, warning for pitfalls, danger for data loss or breaking changes, success for recommended practice.
- Tabs only for per-version or per-OS variants.
- One H1 per page, H2 for sections, H3 sparingly.
- Front matter `description` values are quoted strings, because an unquoted colon breaks the GitBook import.
