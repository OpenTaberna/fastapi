from functools import lru_cache

from app.shared.config import get_settings

from ..adapters import ImapSmtpMailAdapter
from ..adapters.interface import MailAdapter


@lru_cache
def get_mail_adapter() -> MailAdapter:
    return ImapSmtpMailAdapter(get_settings())
