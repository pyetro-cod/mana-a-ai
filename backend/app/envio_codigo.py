"""Envio do código de acesso ao cliente.

O provedor é escolhido por OTP_PROVIDER no .env:
- console: escreve o código no terminal da API (só desenvolvimento; bloqueado em prod).
- whatsapp: WhatsApp Cloud API, com um template de autenticação aprovado pela Meta.
"""
import json
import logging
import urllib.error
import urllib.request

from .config import settings

logger = logging.getLogger("mana.otp")

WHATSAPP_API_VERSION = "v21.0"
WHATSAPP_TIMEOUT_SEGUNDOS = 10


class EnvioFalhou(Exception):
    pass


def _enviar_console(telefone: str, codigo: str) -> None:
    logger.warning("[DEV] código de acesso para %s: %s (válido por %s min)",
                   telefone, codigo, settings.otp_expire_minutes)


def _enviar_whatsapp(telefone: str, codigo: str) -> None:
    # NOTE: payload for an "authentication" template with a copy-code button, per the
    # WhatsApp Cloud API docs. Not exercised yet (no verified business account): confirm
    # the template's components in Meta's dashboard before switching OTP_PROVIDER to whatsapp.
    url = (f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/"
           f"{settings.whatsapp_phone_number_id}/messages")
    corpo = {
        "messaging_product": "whatsapp",
        "to": f"55{telefone}",
        "type": "template",
        "template": {
            "name": settings.whatsapp_template,
            "language": {"code": "pt_BR"},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": codigo}]},
                {"type": "button", "sub_type": "url", "index": "0",
                 "parameters": [{"type": "text", "text": codigo}]},
            ],
        },
    }
    requisicao = urllib.request.Request(
        url,
        data=json.dumps(corpo).encode(),
        headers={"Authorization": f"Bearer {settings.whatsapp_token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=WHATSAPP_TIMEOUT_SEGUNDOS) as resposta:
            if resposta.status >= 300:
                raise EnvioFalhou(f"WhatsApp respondeu {resposta.status}")
    except urllib.error.HTTPError as exc:
        # Log the provider's reason, never the code itself.
        logger.error("WhatsApp recusou o envio (%s): %s", exc.code, exc.read()[:500])
        raise EnvioFalhou("WhatsApp recusou o envio") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.error("Falha de rede ao chamar o WhatsApp: %s", exc)
        raise EnvioFalhou("WhatsApp indisponível") from exc


def enviar_codigo(telefone: str, codigo: str) -> None:
    if settings.otp_provider == "whatsapp":
        _enviar_whatsapp(telefone, codigo)
    else:
        _enviar_console(telefone, codigo)
