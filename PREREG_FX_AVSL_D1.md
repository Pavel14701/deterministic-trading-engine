# PREREG: FX AVSL D1 — первая семья на battery v2

Frozen 2026-09-25, до прогона. Один ран. Порог ENB (§8) уже откалиброван
и заморожен (eceed6d) — для этой семьи НЕ меняется.

## Hypothesis
AVSL-cross engine (промоутед-геометрия: вход на кросс AVSL(70,345),
exit по обратному кроссу, стоп max(|close-line|, 2xATR14), S1 vol-target
sizing) переносится на FX daily majors/crosses: long drift capture
существуют и на FX, а низкая корреляция accrual-стримов даст ENB,
измеримый в отличие от crypto-книги.

## Объявленные приоры (honesty)
- DECOMPOSITION E2: идентичный пайплайн на 1D в crypto МЁРТВ
  (11th pct 1D null). Т.е. это тест переноса, не повторения.
- FX daily trend-following по литературе слаб (низкий drift,
  mean-reversion на горизонте дней). Ожидается честный FAIL;
  battery существует, чтобы это сказать.
- 7 из 10 пар имеют USD-ногу: ожидаем НИЗКИЙ ENB (USD-фактор) —
  это диагностика, ради которой семья и запускается.

## Universe (10 пар, правило выбора объявлено до прогона)
7 G10 USD-мажоры по ликвидности: EURUSD, GBPUSD, USDJPY, AUDUSD,
USDCAD, USDCHF, NZDUSD + 3 старших кросса: EURJPY, GBPJPY, EURGBP.
Источник: yfinance `=X` daily, period=max (EURUSD: 2003-12 -> н.в.,
~5900 баров). Кэш в data/yf/fx_<PAIR>_1D.parquet.

## Data rules
- Валидный бар: Close не-NaN. Сетка: объединение дат всех 10 пар
  (global calendar); e0/e1 пары = позиции её дат в global grid.
- OHLC реальные (High/Low yf отдаёт); vol для fast_line = ones
  (как в synthetic null; объём FX не торгуется).
- Factor: DXY (DX-Y.NYB) daily, momentum 30 дней (объявленная
  подмена BTC-30d). Если <50 выровненных пар в сегменте — ortho_ev=NaN
  с дисклоужером.

## Frozen config (перенос промоутеда; 1D-константы объявлены здесь)
- entry: close пересекает fast_line(Low, Close, ones; 70/345, stand_div 2.0)
  [импорт из engine.passed.avsl_cross_s1]; WARMUP 400 баров
- stop: max(|close-line|, 2 x ATR14) на баре входа; стоп wins intrabar
- exit: первый ОБРАТНЫЙ кросс (close), без TP; иначе MTM на t+HORIZON
- HORIZON = 100 (100 дней ~ 3.3 мес; аналог 500 4H-баров = 83 дня)
- fee: 0.5 bp/сторона (TAKER_FEE=5e-5; 1 pip RT мажоров ~1bp);
  fee_r = 2*fee*close/risk
- sizing S1: size = clip(0.20/rv100, 0.25, 2.0); rv100 = std(100
  предвходных log-ретернов) x sqrt(ANN_D1); ANN_D1 = 365; NaN -> 1.0
- account: bar return = 1% x sum(sized R accrual / hold)

## Battery v1 gates (обе сегмента, PRIMARY = первые 2/3 grid)
- G1 Sharpe_NW >= 1.0 (nw_sharpe, lags=100, ann=365 — импорт);
  ОБЯЗАТЕЛЬНЫЕ дисклоужеры: plain_ann = mean/std x sqrt(365) и
  eff_n = (sum net)^2 / sum(net^2) по сделкам сегмента
- G2 DD <= 25% (portfolio_dd — импорт)
- G3 net EV >= +0.10R
- G4 >= 7/10 пар с положительным средним net в сегменте
- CI: circular block bootstrap, block=100, 1000 draws, seed=11
  (block_bootstrap_ci — импорт), excludes 0

## Battery v2 gates (добавляются к v1)
- G-ENB: ENB >= 2.0 на активных барах (battery_v2.enb)
- G-CONC: conc p95 <= 6, p50/max read-out (battery_v2.concurrency)
- G-CONC p50 — обязательно <= 4 (иначе FAIL-CORR по определению
  «режим определяет число позиций»)
- R3 legs (long/short: n, EV, DD, hold, ex-top20, top20 share)
- R4 exit attribution по reason
- R5 ortho_ev: регрессия net на DXY-30d momentum по fbar входа
- R7 CI_xs = CI_time (известное тождество, eceed6d) — печатается

## Verdict semantics
- v1 FAIL -> семья FX-AVSL закрыта навсегда (kill-правило).
- v1 PASS + G-ENB/G-CONC fail -> FAIL-CORR: universe (FX majors D1)
  закрыт для этого класса сигналов, hypothesis открыта для других
  университетов/TF.
- Всё PASS -> candidate для promotion (prereg promotion отдельно).

## Запрещено
- Трогать пороги после прогона. Второй ран без нового prereg.
- Тюнинг universe/TF/параметров по результату.
