# Synthetic Screens

This folder contains generated demo screenshots. They are synthetic and do not represent real companies.
`manifest.json` is regenerated with labels for scenario category and expected risk fixture.

Initial target set:

- subscription-cancel-retention.png
- subscription-cancel-confirmation.png
- subscription-pause-offer.png
- trial-renewal-warning.png
- trial-discount-retention.png
- trial-cancel-success.png
- checkout-preselected-addon.png
- checkout-donation-addon.png
- checkout-warranty-addon.png
- checkout-no-preselected-addon.png
- marketing-consent-optional.png
- marketing-separated-optional.png
- consent-required-only.png
- account-delete-retention.png
- account-delete-confirmation.png

Regenerate:

```powershell
.\apps\api\.venv\Scripts\python.exe .\scripts\Generate-SyntheticScreens.py
```
