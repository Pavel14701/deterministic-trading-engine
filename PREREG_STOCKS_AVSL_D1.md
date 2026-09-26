# PREREG: STOCKS AVSL D1 (calendar-matched) -- valid transfer test A

Frozen 2026-09-25, до прогона. Один ран. Battery v2 (заморожена,
eceed6d). Appends to the trail after methodological correction 84bd2fd.

## Config-mapping table (NEW RULE, обязательна)
| param       | crypto 4H (target) | stocks D1 (this test) | calendar |
|-------------|--------------------|-----------------------|----------|
| fast        | 70 bars            | 12 bars               | 11.7d -> 12d |
| slow        | 345 bars           | 58 bars               | 57.5d -> 58d |
| WARMUP      | 400 bars           | 67 bars               | 66.7d -> 67d |
| HORIZON     | 500 bars           | 83 bars               | 83.3d -> 83d |
| NW_LAGS     | 500                | 83                    | = HORIZON |
| BOOT block  | 500                | 83                    | = HORIZON |
| ANN (S1, plain) | 6*365=2190     | 252                   | trading days |
| fee         | 5bp/side           | 5bp/side (10bp RT)    | parity, honest |

Проверка: 12d = 12.0d vs 11.7d, 58d = 58.0d vs 57.5d, 83d vs 83.3d,
67d vs 66.7d -- calendar-equivalence ok.

## Universe (survivorship -- declared upward bias, митигации нет)
Те же 12 ликвидных мегакапов: AAPL MSFT NVDA AMZN GOOGL META TSLA
JPM XOM JNJ WMT PG. Все торги в грид-окне; поздние листинги
(GOOGL 2004, TSLA 2010, META 2012) входят по мере данных.

## Regime-homogeneous window + split
Грид обрезан: старт 2001-01-02 (post-decimalization, электронные
рынки). PRIMARY = первые 2/3 грида (2001 ~ 2017.6), F3 = 2017.6-2026.
Один режим микроструктуры по возможности; Reg NMS 2005 внутри --
дисклоужер, не исключаем.

## Data rules
- yf auto_adjust=True (split+div adjusted, total-return-ish);
- volume = dollar volume (close x max(volume,1)) -- primary;
  vol=ones -- объявленный control read-out (verdict не меняет);
- ATR14 стандартный (гэпы включены в TR -- консервативно:
  шире стопы); специальная gap-обработка НЕ вводится, разница
  с криптой дисклоужер;
- factor для R5: SPY 30d momentum (подмена BTC-30d), объявлена;
  <50 пар в сегменте -> ortho NaN.

## Engine (заморожен, перенос)
entry: close x fast_line(Low, Close, vol; FAST=12, SLOW=58,
stand_div 2.0) кросс (та же passed-механика, параметры из таблицы);
stop: max(|close-line|, 2 x ATR14) на баре входа, intrabar стоп wins;
exit: первый обратный кросс, иначе MTM на t+HORIZON (83); без TP.
S1: clip(0.20/rv100, 0.25, 2.0), rv100 = std(100 log-ret) x sqrt(252).

## Gates (оба сегмента)
v1: Sharpe_NW >= 1.0 (lags 83, ann 252); DD <= 25%; net EV >= +0.10R;
pos >= 8/12; CI (block 83, 1000 draws, seed 11) excludes 0.
Дисклоужеры: plain_ann, eff_n, per-year.
v2: G-ENB >= 2.0 (активные бары); G-CONC p95 <= 6 и p50 <= 4;
legs (long/short); exit attribution; ortho_ev vs SPY-30d.

## Verdict semantics
FAIL -> семья stocks-AVSL-D1(12,58) закрыта навсегда.
FAIL-CORR -> universe закрыт для класса, hypothesis открыта.
PASS -> candidate (promotion-prereg отдельно).

## Дисклоужеры вне гейтов
- survivorship: любой PASS смещён вверх, перед live-scale обязателен
  point-in-time universe тест;
- short borrow не смоделирован -> шортовая нога завышена;
- Reg NMS 2005 внутри PRIMARY.

## Запрещено
Менять пороги/параметры после прогона. Второй ран = новый prereg.
