"""
Generates an HTML backtest report from stats produced by backtest.py.
Output: reports/SYMBOL_TF_report.html
"""

import os
import pandas as pd
from datetime import datetime


def generate_report(stats: dict, symbol: str, setup_tf: str, entry_tf: str, years: int):
    os.makedirs("reports", exist_ok=True)

    df: pd.DataFrame = stats["trades_df"]
    by_symbol        = stats["by_symbol"]

    # Equity curve data
    equity_points = []
    running_pnl   = 0.0
    for _, row in df.iterrows():
        running_pnl += row["pnl_usd"]
        equity_points.append({
            "time": str(row["entry_time"]),
            "pnl":  round(running_pnl, 2),
        })

    equity_labels = [p["time"] for p in equity_points]
    equity_values = [p["pnl"] for p in equity_points]

    # Trade log rows
    rows_html = ""
    for _, row in df.iterrows():
        color = "#d4edda" if row["result"] == "TP" else "#f8d7da"
        rows_html += f"""
        <tr style="background:{color}">
            <td>{row['entry_time']}</td>
            <td>{row['exit_time']}</td>
            <td>{row['symbol']}</td>
            <td>{row['entry_price']}</td>
            <td>{row['sl_price']}</td>
            <td>{row['tp_price']}</td>
            <td>{row['exit_price']}</td>
            <td>{row.get('mother_high', '')}</td>
            <td>{row.get('mother_low', '')}</td>
            <td>{row['sl_pips']}</td>
            <td>{row['rr_planned']}</td>
            <td>{row['rr_achieved']}</td>
            <td><b>{row['result']}</b></td>
            <td>${row['pnl_usd']}</td>
            <td>{row['duration_mins']} min</td>
        </tr>"""

    # Per-symbol rows
    sym_rows = ""
    for sym, data in by_symbol.items():
        wr = round(data["wins"] / data["trades"] * 100, 1) if data["trades"] else 0
        sym_rows += f"""
        <tr>
            <td>{sym}</td>
            <td>{data['trades']}</td>
            <td>{data['wins']}</td>
            <td>{data['trades'] - data['wins']}</td>
            <td>{wr}%</td>
            <td>${round(data['pnl'], 2)}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Backtest Report — {symbol}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  body {{ font-family: Arial, sans-serif; margin: 30px; background: #f5f5f5; color: #333; }}
  h1   {{ color: #2c3e50; }}
  h2   {{ color: #2c3e50; border-bottom: 2px solid #2c3e50; padding-bottom: 5px; margin-top: 40px; }}
  .summary-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 15px;
    margin: 20px 0;
  }}
  .card {{
    background: #fff;
    border-radius: 8px;
    padding: 15px 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1);
    text-align: center;
  }}
  .card .value {{ font-size: 1.6em; font-weight: bold; color: #2c3e50; }}
  .card .label {{ font-size: 0.8em; color: #888; margin-top: 4px; }}
  .positive {{ color: #27ae60 !important; }}
  .negative {{ color: #e74c3c !important; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: #fff;
    box-shadow: 0 1px 4px rgba(0,0,0,0.1);
    border-radius: 8px;
    overflow: hidden;
    font-size: 0.85em;
  }}
  th {{
    background: #2c3e50;
    color: #fff;
    padding: 10px 8px;
    text-align: left;
  }}
  td {{ padding: 8px; border-bottom: 1px solid #eee; }}
  tr:last-child td {{ border-bottom: none; }}
  .chart-container {{ background: #fff; padding: 20px; border-radius: 8px;
                       box-shadow: 0 1px 4px rgba(0,0,0,0.1); margin: 20px 0; }}
</style>
</head>
<body>

<h1>Backtest Report — {symbol} ({setup_tf} Setup / {entry_tf} Entry)</h1>
<p style="color:#888">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp; Data: {years} year(s)</p>

<h2>Summary</h2>
<div class="summary-grid">
  <div class="card"><div class="value">{stats['total_trades']}</div><div class="label">Total Trades</div></div>
  <div class="card"><div class="value">{stats['wins']} / {stats['losses']}</div><div class="label">Wins / Losses</div></div>
  <div class="card"><div class="value">{stats['win_rate']}%</div><div class="label">Win Rate</div></div>
  <div class="card"><div class="value {'positive' if stats['total_pnl_usd'] >= 0 else 'negative'}">${stats['total_pnl_usd']}</div><div class="label">Total P&amp;L (USD)</div></div>
  <div class="card"><div class="value">{stats['profit_factor']}</div><div class="label">Profit Factor</div></div>
  <div class="card"><div class="value negative">${stats['max_drawdown_usd']}</div><div class="label">Max Drawdown</div></div>
  <div class="card"><div class="value">{stats['avg_rr_achieved']}</div><div class="label">Avg RR Achieved</div></div>
  <div class="card"><div class="value">{stats['avg_duration_mins']} min</div><div class="label">Avg Trade Duration</div></div>
  <div class="card"><div class="value">{stats['max_consec_losses']}</div><div class="label">Max Consec. Losses</div></div>
</div>

<h2>Equity Curve</h2>
<div class="chart-container">
  <canvas id="equityChart" height="80"></canvas>
</div>

<h2>Per-Symbol Breakdown</h2>
<table>
  <tr><th>Symbol</th><th>Trades</th><th>Wins</th><th>Losses</th><th>Win Rate</th><th>P&amp;L (USD)</th></tr>
  {sym_rows}
</table>

<h2>Trade Log</h2>
<table>
  <tr>
    <th>Entry Time</th><th>Exit Time</th><th>Symbol</th>
    <th>Entry</th><th>SL</th><th>TP</th><th>Exit</th>
    <th>Mother High</th><th>Mother Low</th>
    <th>SL Pips</th><th>RR Plan</th><th>RR Got</th>
    <th>Result</th><th>P&amp;L</th><th>Duration</th>
  </tr>
  {rows_html}
</table>

<script>
const ctx = document.getElementById('equityChart').getContext('2d');
new Chart(ctx, {{
  type: 'line',
  data: {{
    labels: {equity_labels},
    datasets: [{{
      label: 'Cumulative P&L (USD)',
      data: {equity_values},
      borderColor: '#2c3e50',
      backgroundColor: 'rgba(44,62,80,0.1)',
      borderWidth: 2,
      pointRadius: 2,
      fill: true,
      tension: 0.3,
    }}]
  }},
  options: {{
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ display: false }},
      y: {{ grid: {{ color: '#eee' }} }}
    }}
  }}
}});
</script>
</body>
</html>"""

    filename = f"reports/{symbol}_{setup_tf}_{entry_tf}_{years}y_report.html"
    with open(filename, "w") as f:
        f.write(html)

    print(f"Report saved: {filename}")
    return filename
