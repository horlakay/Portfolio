# Partner Center Checklist

Use this checklist before attempting a Microsoft Store submission.

## Product identity

- [ ] Reserve the product name in Partner Center:
  - `SentinelStream Analyst Desktop`
- [ ] Confirm the publisher account name is the one you want users to see
- [ ] Decide whether the app will be free, paid, or trial-based

## Runtime model

- [ ] Finalize the supported release mode
- [ ] Remove the need for developer-only setup in the public product experience
- [ ] Decide whether the public app will:
  - connect to a hosted SentinelStream backend
  - include a true local demo mode
  - support both

## Installer/package

- [ ] Choose the submission route:
  - EXE/MSI
  - MSIX
- [ ] Ensure the release build is versioned
- [ ] Ensure the installer is stable and reproducible
- [ ] If using EXE submission:
  - [ ] sign the installer with a trusted code-signing certificate
  - [ ] host the installer at a versioned HTTPS URL
  - [ ] confirm the installer is offline and not a downloader stub
- [ ] If using MSIX submission:
  - [x] MSIX/AppX build target wired in `package.json` (`npm run dist:appx`)
  - [ ] fill in real `identityName`, `publisher`, and `publisherDisplayName`
        in the `build.appx` block from your Partner Center reservation
  - [ ] create the MSIX package on Windows (`npm run dist:appx`)
  - [ ] validate it with the Windows App Certification Kit (WACK)

## Store listing assets

- [ ] 1 required screenshot for the PC device family
- [ ] 4 to 8 recommended screenshots showing key workflows
- [ ] 1 required Store logo
- [ ] optional poster art / additional promotional images
- [ ] short description
- [ ] long description
- [ ] feature list
- [ ] support URL
- [ ] privacy policy URL

## Policy and trust

- [ ] Review Microsoft Store policies before submission
- [ ] Verify the app's privacy policy reflects actual data handling
- [ ] Make sure support information is public and current
- [ ] Review telemetry, logging, and authentication language for user-facing clarity

## App experience checks

- [ ] Replace default Electron icon with production branding
- [ ] Validate first-run experience on a clean Windows machine
- [ ] Validate install, launch, upgrade, and uninstall behavior
- [ ] Validate app behavior without a developer shell or repo checkout
- [ ] Confirm startup failure states remain clear and user-friendly

## Current status in this repo

Completed:

- [x] Windows EXE artifacts are being produced
- [x] Embedded and external desktop modes exist
- [x] Local settings persistence exists
- [x] Installer and portable build outputs are named cleanly

Not completed:

- [ ] production icon assets
- [ ] public privacy policy URL
- [ ] public support URL
- [ ] signed installer
- [ ] hosted versioned HTTPS installer URL
- [ ] final end-user runtime model
- [ ] Store screenshots and Store logo pack

Partially completed:

- [~] MSIX packaging workflow (build target wired via `npm run dist:appx`;
  still needs real Partner Center identity values and a WACK validation pass)

## Go/No-Go

Current decision: `NO-GO` for Microsoft Store submission

Reason:

The app is not yet fully productized for end users, and the Store submission
requirements around hosted installers, signing, branding, and public policy
pages are not finished.
