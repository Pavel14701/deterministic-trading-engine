# PREREG: FX AVSL 4H (config preserved) -- valid transfer test B

Frozen 2026-09-25, до прогона. Один ран. Battery v2 (eceed6d).
Appends to the trail after correction 84bd2fd.  Data: Dukascopy
(данные уже в руках на момент freeze -- fetch идёт, файлы до
freeze не просматривались и не анализировались).

## Config-mapping table (NEW RULE)
| param       | crypto 4H (target) | FX 4H (this test)    | note |
|-------------|--------------------|----------------------|------|
| fast/slow   | 70/345 bars        | 70/345 bars          | IDENTICAL -- same bar length, same timescale |
| WARMUP      | 400                | 400                  | copy |
| HORIZON     | 500                | 500                  | copy |
| NW_LAGS     | 500                | 500                  | copy |
| BOOT block  | 500                | 500                  | copy, seed 11 |
| S1 ANN      | sqrt(6*365)=2190   | sqrt(6*260)=sqrt(1560) | 6 bars/day (24h/4h), 260 trading days/yr FX; НЕ 260 (это для D1) |
| fee         | 5bp/side           | 0.5bp/side (1 pip RT majors) | рынок дешевле, declared |
| K_STOP      | 2.0                | 2.0                  | copy |
| volume      | real traded        | TICK volume (proxy)  | см. ниже |

Calendar equivalence: полный конфиг-копия -- это и есть тест
"тот же сигнал, другой universe".

## Universe
Те же 10 пар (7 majors + EURJPY/GBPJPY/EURGBP). Dukascopy bid-side
4H бары. Coverage: majors с 2003 (дисклоужер после прогона).

## Declared limitations
- VOLUME = tick count, не traded volume (OTC).  Если AVSL-эдж
  требует реального объёма, FX может дать FAIL из-за прокси.
  Поэтому: PRIMARY = tick volume; vol=ones = объявленный control
  read-out (verdict не меняет).  Расхождение primary/control --
  само по себе диагностик.
- OHLC = BID (крипта была last-trade) -- дисклоужер.
- Weekend/rollover гэпы входят в ATR14 и rolling-окна; сессионных
  фильтров НЕТ (объявлено).  Бар-грид плотный по торговым часам.
- factor R5: DXY 30d daily momentum, fbar = последний завершённый
  день (тот же механизм, что BTC-30d в battery v2).

## Gates (оба сегмента, PRIMARY = 2/3 общего грида)
v1: Sharpe_NW >= 1.0; DD <= 25%; net EV >= +0.10R; pos >= 7/10;
CI (block 500, 1000 draws, seed 11) excludes 0.
Дисклоужеры: plain_ann, eff_n, per-year.
v2: G-ENB >= 2.0 (активные бары); G-CONC p95 <= 6, p50 <= 4;
legs (long/short); exit attribution; ortho_ev vs DXY-30d.

## Verdict semantics
FAIL -> семья FX-AVSL-4H(70,345) закрыта навсегда.
FAIL-CORR -> universe закрыт для класса, hypothesis открыта.
PASS -> candidate для promotion (prereg отдельно).

## Запрещено
Менять пороги/параметры после прогона.  Второй ран = новый prereg.
