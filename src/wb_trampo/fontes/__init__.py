"""Sites de onde o robô coleta vagas. Para adicionar um site, crie um módulo que siga
a interface de `base.Fonte` e registre-o em FONTES."""

from .base import Fonte
from .gupy import Gupy
from .linkedin import LinkedIn

FONTES: dict[str, Fonte] = {"linkedin": LinkedIn(), "gupy": Gupy()}

NAO_SUPORTADOS = {
    "indeed": "o Indeed bloqueia robôs com uma verificação (Cloudflare) e o wb_trampo não tenta burlar isso",
}
