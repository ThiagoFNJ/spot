from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
BRONZE = DATA / "bronze"
SILVER = DATA / "silver"
SEEDS = DATA / "seeds"

LEG_SYS_HOST = "http://45.4.247.157"
LEG_SYS_BASE = f"{LEG_SYS_HOST}/leg/salvador"
SYSINF_HOST = "https://cmsalvador.sys.inf.br"
CMS_SITE = "https://www.cms.ba.gov.br"
DIOLY_API = "https://portal-api.dioly.com.br/api"

USER_AGENT = "spot-cms-monitor/0.1 (+https://github.com/thiagonogueira/spot)"
MIN_GAP_SECONDS = 1.0

# Escopo do MVP: legislatura 2025-2028.
MVP_START = "2025-01"

TIPOS_SESSAO = {1: "Sessão Ordinária", 2: "Sessão Especial", 3: "Sessão Solene", 4: "Sessão Extraordinária"}
