import sys
from pathlib import Path
import os

# Ensure backend is in path
backend_path = Path.cwd() / "backend"
sys.path.append(str(backend_path))

# Setup dummy env if needed
os.environ["STOCK_UNIVERSE"] = "NIFTY100"

try:
    print("Importing generate_signals...")
    from app.engine.signal_generator import generate_signals
    
    print("Starting generation...")
    # Force single worker to avoid thread pool hiding errors (though TP usually prints em)
    # But wait, generate_signals accepts max_workers.
    results = generate_signals(strategy_type="swing", max_signals=1, max_workers=1)
    print(f"Generated {len(results)} signals")
    
except Exception as e:
    import traceback
    traceback.print_exc()
