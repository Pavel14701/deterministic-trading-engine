#!/usr/bin/env bash
# Sequential trades fetch for the ETH subset (wave 2).  Checkpoint: one
# file per instrument; skip existing.  On non-200: wait 90s and
# retry (max 4), then move on (missing files re-picked on rerun).
set -u
REPO="$(cd "$(dirname "$0")/../../.." && pwd)" || exit 1
cd "$REPO" || exit 1
echo "repo: $REPO" >&2
OUT=data/deribit/btc_full_trades
mkdir -p "$OUT"
N=0; TOTAL=$(wc -l < data/deribit/btc_full_names.txt)
while read -r name; do
  name=${name%$""}
  [ -s "$OUT/$name.json" ] && continue
  N=$((N+1))
  end_ms=$(($(date -d "$name" +%s 2>/dev/null || echo 0)000))
  url="https://history.deribit.com/api/v2/public/get_last_trades_by_instrument?instrument_name=$name&include_old=true&count=10000"
  code=$(curl -s --max-time 30 -o "$OUT/$name.tmp" -w "%{http_code}" "$url")
  if [ "$code" != "200" ]; then
    for wait in 90 120 150 180; do
      echo "$(date +%H:%M:%S) $name code=$code retry in ${wait}s" >&2
      sleep "$wait"
      code=$(curl -s --max-time 30 -o "$OUT/$name.tmp" -w "%{http_code}" "$url")
      [ "$code" = "200" ] && break
    done
  fi
  if [ "$code" = "200" ]; then
    mv "$OUT/$name.tmp" "$OUT/$name.json"
  else
    rm -f "$OUT/$name.tmp"
    echo "$(date +%H:%M:%S) FAILED $name ($code)" >&2
  fi
  [ $((N % 25)) -eq 0 ] && echo "$(date +%H:%M:%S) progress $N/$TOTAL"
  sleep 1.5
done < data/deribit/btc_full_names.txt
echo "DONE. fetched files: $(ls "$OUT" | wc -l)/$TOTAL"
