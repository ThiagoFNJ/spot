#!/usr/bin/env bash
# Roda no droplet, por cron, uma vez por dia: puxa main, relê o que muda nas fontes e regenera os
# dados; se o código ou os dados mudaram desde o último build, constrói o site (um build só para
# todas as cidades) e o publica em /root/g0v/site/vereadores.
#
#   capitais (frontend/data/cities.json): o ETL de cada uma (Rio, São Paulo), como antes
#   municípios do Estado do Rio: TSE (zips cacheados em data/raw/tse/, rebaixados só quando o TSE
#     os atualiza e a cópia tem mais de 7 dias), SAPL das câmaras que o usam (incremental, 1 req/s
#     por câmara) e o export de frontend/data/rjm/
#
# Cada parte que roda bem guarda os seus arquivos em $DIR/data-ok-vereadores/ (o último snapshot bom). Se uma
# parte falha, ela segue com o último snapshot bom ou, sem ele, com o commitado em main; as outras
# não param. Falhas avisam por e-mail.
#
#   /root/g0v/build-vereadores.sh               # só reconstrói se algo mudou
#   FORCE=1 /root/g0v/build-vereadores.sh       # reconstrói de qualquer jeito
#   SKIP_DATA=1 /root/g0v/build-vereadores.sh   # não lê nenhuma fonte; usa o último snapshot bom do servidor
set -euo pipefail
export PATH=/usr/local/bin:/usr/bin:/bin

REPO="${REPO:-https://github.com/Tomoyo-Computer-Science-Research-Unit/como-votou.git}"
DIR="${DIR:-/root/g0v}"
SRC="$DIR/src-vereadores"
MARK="$DIR/.vereadores-built"
RUNS="$DIR/runs-vereadores.jsonl"
BASE_PATH="/vereadores"
ALERT_TO="${ALERT_TO:-arete@tomoyo.systems}"
export NEXT_TELEMETRY_DISABLED=1
export NODE_OPTIONS="--max-old-space-size=2048"

started="$(date +%s)"
key=""
note=""

log() { echo "$(date -Is) $*"; }

record() {
  python3 - "$1" "${2:-}" "$key" "$(( $(date +%s) - started ))" >> "$RUNS" <<'PY'
import datetime, json, sys
print(json.dumps({
    "at": datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds"),
    "result": sys.argv[1], "detail": sys.argv[2] or None, "key": sys.argv[3] or None, "duration_s": int(sys.argv[4]),
}, ensure_ascii=False))
PY
}

notify() {
  printf 'From: g0v <g0v@tomoyo.systems>\nTo: %s\nSubject: %s\nContent-Type: text/plain; charset=utf-8\n\n%s\n' "$ALERT_TO" "$1" "$2" \
    | docker exec -i mailserver sendmail -t || log "aviso por e-mail falhou"
}

on_error() {
  log "falhou na linha $1"
  record "falhou" "linha $1"
  notify "[como-votou] rodada falhou" "O build-vereadores.sh parou na linha $1 em $(hostname). Veja $DIR/build-vereadores.log."
}
trap 'on_error $LINENO' ERR

[ -d "$SRC/.git" ] || git clone -q "$REPO" "$SRC"
git -C "$SRC" fetch -q origin main
git -C "$SRC" reset -q --hard origin/main
rev="$(git -C "$SRC" rev-parse --short HEAD)"

if [ -f "$SRC/deploy/build-site.sh" ] && ! cmp -s "$SRC/deploy/build-site.sh" "$0"; then
  cp "$SRC/deploy/build-site.sh" "$0"
  chmod 755 "$0"
  log "script atualizado a partir de $rev; recomeçando"
  exec "$0" "$@"
fi

PY="$SRC/backend/.venv/bin/python"
[ -x "$PY" ] || uv venv -q --python 3.12 "$SRC/backend/.venv"
uv pip install -q --python "$PY" -e "$SRC/backend"

OK="$DIR/data-ok-vereadores"

keep_ok() {   # $1 = caminho relativo a frontend/data (pasta ou arquivo): guarda como último snapshot bom
  mkdir -p "$(dirname "$OK/$1")"
  if [ -d "$SRC/frontend/data/$1" ]; then
    rsync -a --delete "$SRC/frontend/data/$1/" "$OK/$1/"
  else
    cp "$SRC/frontend/data/$1" "$OK/$1"
  fi
}

restore() {   # $1 = caminho relativo a frontend/data: último snapshot bom, ou o de main
  if [ -e "$OK/$1" ]; then
    if [ -d "$OK/$1" ]; then rsync -a --delete "$OK/$1/" "$SRC/frontend/data/$1/"; else cp "$OK/$1" "$SRC/frontend/data/$1"; fi
    log "$1: último snapshot bom"
  else
    git -C "$SRC" checkout -q -- "frontend/data/$1" && git -C "$SRC" clean -fdq -- "frontend/data/$1"
    log "$1: snapshot de main"
  fi
}

run_etl() {   # $1 = sigla da capital (cities.json)
  local uf="$1" lower etl_output
  lower="$(echo "$uf" | tr 'A-Z' 'a-z')"
  if etl_output="$(cd "$SRC/backend" && "$PY" -m app.etl.export_snapshot --uf "$uf" --all 2>&1 && "$PY" -m app.etl.export_static_frontend --uf "$uf" 2>&1)"; then
    log "ETL $uf ok"
    keep_ok "$lower"
  else
    log "ETL $uf falhou"
    note="${note:+$note; }ETL $uf falhou"
    notify "[como-votou] ETL $uf falhou" "$(printf '%s\n\n%s' "A leitura da Câmara ($uf) falhou; essa cidade segue com o último snapshot bom." "$etl_output" | tail -c 6000)"
    restore "$lower"
  fi
}

run_municipios() {
  local out started_m
  started_m="$(date +%s)"
  if out="$(cd "$SRC/backend" && "$PY" -m app.etl.tse_rj 2>&1 && { "$PY" -m app.etl.sapl --all 2>&1 || true; } && "$PY" -m app.etl.municipios 2>&1)"; then
    log "municípios ok em $(( $(date +%s) - started_m )) s"
    keep_ok rjm
    keep_ok rj-municipios.json
    if echo "$out" | grep -q '^falharam:'; then
      note="${note:+$note; }SAPL: $(echo "$out" | grep '^falharam:' | tail -1)"
    fi
  else
    log "municípios falharam"
    note="${note:+$note; }municípios falharam"
    notify "[como-votou] municípios do RJ falharam" "$(printf '%s\n\n%s' "TSE, SAPL ou o export dos municípios falhou; eles seguem com o último snapshot bom." "$out" | tail -c 6000)"
    restore rjm
    restore rj-municipios.json
  fi
}

CITIES="$(python3 -c 'import json,sys; [print(c["uf"], c["slug"], int(bool(c.get("root")))) for c in json.load(open(sys.argv[1]))["cities"]]' "$SRC/frontend/data/cities.json")"

if [ "${SKIP_DATA:-0}" = "1" ]; then
  while read -r _uf slug _root; do
    [ -e "$OK/$slug" ] && restore "$slug"
  done <<< "$CITIES"
  [ -e "$OK/rjm" ] && restore rjm && restore rj-municipios.json
else
  while read -r uf _slug _root; do
    run_etl "$uf"
  done <<< "$CITIES"
  run_municipios
fi

key="$rev $(cd "$SRC" && "$PY" - <<'PY'
import hashlib, json, pathlib
h = hashlib.sha256()
for name in sorted(str(p) for p in pathlib.Path("frontend/data").rglob("*.generated.json")):
    data = json.loads(pathlib.Path(name).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data.pop("generated_at", None)
        for source in data.get("sources", []) if isinstance(data.get("sources"), list) else []:
            source.pop("accessed_at", None)
    h.update(name.encode())
    h.update(json.dumps(data, sort_keys=True, separators=(",", ":")).encode())
print(h.hexdigest()[:16])
PY
)"

if [ "${FORCE:-0}" != "1" ] && [ -f "$MARK" ] && [ "$(cat "$MARK")" = "$key" ]; then
  log "sem mudança ($key)"
  record "sem mudança" "$note"
  exit 0
fi

log "construindo ($key)"
(cd "$SRC/frontend" && npm ci --no-audit --no-fund --silent && NEXT_PUBLIC_BASE_PATH="$BASE_PATH" npm run build --silent >/dev/null)
# Um build só: Rio na raiz, São Paulo em sp/, os municípios em rj/<slug>/, os dados em data/.
mkdir -p "$DIR/site$BASE_PATH"
rsync -a --delete --chmod=D755,F644 "$SRC/frontend/out/" "$DIR/site$BASE_PATH/"
echo "$key" > "$MARK"
record "publicado" "$note"
log "publicado ($key)"
