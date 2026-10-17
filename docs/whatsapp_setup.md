# WhatsApp setup (Meta Cloud API)

Everything here needs a Meta developer account and is done by a human. Nothing in the repo contains real credentials. Until these steps are done, `WHATSAPP_ENABLED=false` and the channel is tested only against a mocked Graph API.

## 1. Create the app and test number
1. developers.facebook.com → Create App → type Business → add the **WhatsApp** product.
2. In WhatsApp → API Setup, note the **test phone number**, its **Phone number ID**, and generate a token.
3. Add up to five **recipient numbers** (test numbers only message pre-registered recipients). Collect evaluator numbers through the submission form.
4. Create a **permanent token** with a system user (the temporary token expires in 24 hours).
5. App Settings → Basic → copy the **App secret**.

## 2. Environment variables (Render dashboard, never in git)

| Variable | Value |
|---|---|
| `WHATSAPP_ENABLED` | `true` |
| `WHATSAPP_PHONE_NUMBER_ID` | from API Setup |
| `WHATSAPP_ACCESS_TOKEN` | permanent token |
| `WHATSAPP_APP_SECRET` | App secret (used to verify `X-Hub-Signature-256`) |
| `WHATSAPP_VERIFY_TOKEN` | a random string you choose |
| `WHATSAPP_DISPLAY_NUMBER` | the number shown on the landing page |
| `WHATSAPP_GRAPH_VERSION` | check the current version in Meta docs |

## 3. Webhook
1. WhatsApp → Configuration → Webhook → Callback URL: `https://<host>/whatsapp/webhook`, Verify token: the value above.
2. Subscribe to the `messages` field.
3. The app answers the verification handshake on `GET /whatsapp/webhook` and rejects any `POST` whose signature does not match the app secret (HTTP 401), or any request when the secret is unset (HTTP 503).

## 4. Templates (needed to message outside the 24-hour window)
Submit the templates in `content/whatsapp_templates.yaml` in WhatsApp Manager as **Utility**, language Hindi. Positional variables `{{1}}`, `{{2}}` must match the file. When Meta approves one, set `approved: true` for it. Until then the app skips and logs out-of-window sends.

## 5. Check it
1. Send "शुरू" from a registered number to the test number.
2. Confirm a reply arrives in Hindi, text first, then audio.
3. `GET /healthz` still returns the deployed SHA; check Render logs for `Invalid webhook HMAC signature` if replies never arrive.
