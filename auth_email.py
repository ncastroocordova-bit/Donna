"""Script de un solo uso: genera los REFRESH TOKENS de correo para Donna.

Gmail (API OAuth):
  1. En Google Cloud → APIs y servicios → Credenciales, crea un OAuth client ID tipo
     "App de escritorio". Copia client_id y client_secret a tu .env (GMAIL_CLIENT_ID/SECRET).
  2. Habilita la "Gmail API" en el proyecto.
  3. Corre:  python auth_email.py gmail   → abre el navegador, autorizas, y te imprime
     el GMAIL_REFRESH_TOKEN para pegar en .env.

Outlook personal (Microsoft Graph):
  1. En Azure Portal → Microsoft Entra ID → Registros de aplicaciones, registra una app.
     Tipos de cuenta: "Solo cuentas personales de Microsoft". Plataforma: cliente público
     (móvil/escritorio). Permiso delegado: Mail.ReadWrite (offline_access va implícito).
     Copia el Application (client) ID a tu .env (OUTLOOK_CLIENT_ID).
  2. Corre:  python auth_email.py outlook   → te da un código para pegar en
     microsoft.com/devicelogin; al autorizar imprime el OUTLOOK_REFRESH_TOKEN.

Sin argumento corre los dos que tengan client_id configurado.
"""
import sys

from config import settings

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
OUTLOOK_SCOPES = ["Mail.ReadWrite"]


def auth_gmail() -> None:
    if not (settings.gmail_client_id and settings.gmail_client_secret):
        print("[Gmail] Falta GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET en .env. Salto.")
        return
    from google_auth_oauthlib.flow import InstalledAppFlow

    config = {
        "installed": {
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(config, scopes=GMAIL_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    print("\n=== Gmail listo ===")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}\n")


def auth_outlook() -> None:
    if not settings.outlook_client_id:
        print("[Outlook] Falta OUTLOOK_CLIENT_ID en .env. Salto.")
        return
    import msal

    app = msal.PublicClientApplication(
        settings.outlook_client_id, authority="https://login.microsoftonline.com/consumers"
    )
    flow = app.initiate_device_flow(scopes=OUTLOOK_SCOPES)
    if "user_code" not in flow:
        print(f"[Outlook] No pude iniciar el device flow: {flow.get('error_description', flow)}")
        return
    print("\n=== Outlook ===")
    print(flow["message"])  # "Ve a microsoft.com/devicelogin e ingresa el código XXXX"
    result = app.acquire_token_by_device_flow(flow)  # bloquea hasta que autorizas
    if "refresh_token" not in result:
        print(f"[Outlook] No obtuve refresh token: {result.get('error_description', result)}")
        return
    print("\n=== Outlook listo ===")
    print(f"OUTLOOK_REFRESH_TOKEN={result['refresh_token']}\n")


def main() -> None:
    objetivo = sys.argv[1].lower() if len(sys.argv) > 1 else "both"
    if objetivo in ("gmail", "both"):
        auth_gmail()
    if objetivo in ("outlook", "both"):
        auth_outlook()
    print("Pega los tokens en tu .env (y en las variables de Railway).")


if __name__ == "__main__":
    main()
