import os
import sys

# Add directory to path to import simulate_smc_2025
sys.path.append(r"c:\Users\shaik\OneDrive\Desktop\Binance Bot")
from simulate_smc_2025 import simulate_smc, STARTING_CAPITAL

print("Running simulation to generate clean markdown log for 2025...")
trades, final, mdd = simulate_smc()
wins = len([t for t in trades if t['pnl'] > 0])

log_path = r"C:\Users\shaik\.gemini\antigravity\brain\064a8ba6-0bdc-4047-9d9e-e8df27b04ca8\smc_2025_trade_log.md"

with open(log_path, 'w', encoding='utf-8') as f:
    f.write("# 2025 SMC Trade Log (50x Leverage)\n\n")
    f.write(f"**Total Trades:** {len(trades)} | **Wins:** {wins} | **WinRate:** {wins/len(trades)*100 if trades else 0:.1f}%\n")
    f.write(f"**Final Capital:** ${final:.2f} (from ${STARTING_CAPITAL:.2f}) | **Max DD:** {mdd:.1f}%\n\n")
    f.write("```text\n")
    for i, t in enumerate(trades):
        m = "+" if t['pnl'] >= 0 else "-"
        f.write(f"#{i+1:<3} {t['dir']:<5} {str(t['time'])[:16]} Entry: ${t['entry']:.0f} Stop: ${t['stop']:.0f} Target: ${t['target']:.0f} -> {t['exit_r']} {m}${abs(t['pnl']):.2f} (Bal: ${t['bal']:.2f})\n")
    f.write("```\n")

print("Log written to:", log_path)
