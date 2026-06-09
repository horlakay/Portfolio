# Microsoft Store Submission Pack

This folder contains the first Store-submission materials for
SentinelStream Analyst Desktop.

It is designed to reduce the final Partner Center work once the product is
ready for public release.

## What's in here

- `partner-center-checklist.md`
  - submission prerequisites and go/no-go checks
- `listing.en-US.md`
  - suggested English listing copy for the Store page
- `privacy-policy.template.md`
  - a privacy policy draft that should be reviewed and published at a public URL
- `support.template.md`
  - a support/contact page draft for the app

## Current recommendation

Do not submit the app to Microsoft Store yet.

The current desktop app is a promising product shell, but it still needs:

1. a stable end-user runtime model
2. production branding and screenshots
3. a public privacy policy URL
4. a public support URL
5. a code-signing plan and hosted versioned installer URL if submitting as EXE

## Suggested app name

`SentinelStream Analyst Desktop`

## Suggested Store category

`Business`

Alternative category depending on final positioning:

`Developer tools`

## Packaging direction

Two viable routes exist:

1. submit the existing signed EXE installer through Partner Center
2. repackage to MSIX for a cleaner Microsoft Store experience

MSIX remains the stronger long-term option, but the current app is closer to
an EXE-based submission path.
