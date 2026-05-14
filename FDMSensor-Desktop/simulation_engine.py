import math
import pandas as pd
import numpy as np
from datetime import datetime

class HermeticSimulationEngine:
    """
    Thermal Simulation Engine for 50 kVA Hermetic Transformer (ONAN).
    Strictly follows the mathematical model in 'termal_simulasyon_tasarimi.md'.
    
    Logic:
    Recursive exponential approach using thermal time constants.
    """
    
    def __init__(self):
        # Constants from Section 2 of design document
        self.P0 = 160.0             # [W] No-load loss
        self.Pk = 1050.0            # [W] Load loss
        self.R = self.Pk / self.P0  # Loss ratio (6.5625)
        self.n = 0.8                # Exp coefficient
        self.dt_top_rated = 60.0    # [K] Top oil rated rise
        self.dt_bot_rated = 45.7    # [K] Bottom oil rated rise
        self.tau_top = 6.0          # [h] Top oil time constant
        self.tau_bottom = 5.0       # [h] Bottom oil time constant

    def run_simulation(self, data_rows, load_factor=1.0):
        """
        Run recursive simulation according to Section 3 of design document.
        
        Args:
            data_rows: List of dicts with 'sensor_timestamp', 'sensor1' (Meas Top), 'sensor2' (Amb), 'sensor3' (Meas Bot)
            load_factor (K): Constant load factor (0.0 to 1.5+)
        """
        if not data_rows:
            return []
            
        # 1. Sort and Prepare Data
        df = pd.DataFrame(data_rows)
        try:
            if 'sensor_timestamp' in df.columns:
                df['dt_obj'] = pd.to_datetime(df['sensor_timestamp'])
            elif 'time' in df.columns:
                df['dt_obj'] = pd.to_datetime(df['time'])
            else:
                return data_rows
        except Exception as e:
            print(f"Simulation Date Error: {e}")
            return data_rows
            
        df = df.sort_values('dt_obj')
        
        # 2. Steady State Values for given Load Factor (K)
        # Multiplier(K) = ((K^2 * R + 1) / (R + 1))^n
        multiplier = (( (load_factor**2) * self.R + 1) / (self.R + 1))**self.n
        dt_ss_top = self.dt_top_rated * multiplier
        dt_ss_bot = self.dt_bot_rated * multiplier
        
        # 3. Recursive Simulation Loop
        enriched_rows = []
        
        # State variables (Delta Theta)
        cur_delta_top = 0.0
        cur_delta_bot = 0.0
        prev_time = None
        
        for i, row in df.iterrows():
            amb = float(row.get('sensor2') or 20.0)
            cur_time = row['dt_obj']
            
            if prev_time is None:
                # Initialization (Section 4.2)
                # Instead of using measurements (which might be from a different load),
                # we initialize with the steady-state rise for the SPECIFIED load_factor.
                # This provides a clean baseline for the simulation window.
                cur_delta_top = dt_ss_top
                cur_delta_bot = dt_ss_bot
                dt_hours = 0.0 # No change in first step
            else:
                dt_hours = (cur_time - prev_time).total_seconds() / 3600.0
            
            # Apply Thermal Time Constant (Formula 3.2)
            # alpha = exp(-dt/tau)
            # Delta[t] = alpha * Delta[t-1] + (1 - alpha) * Delta_ss
            
            if dt_hours > 0:
                alpha_top = math.exp(-dt_hours / self.tau_top)
                alpha_bot = math.exp(-dt_hours / self.tau_bottom)
                
                cur_delta_top = (alpha_top * cur_delta_top) + ((1 - alpha_top) * dt_ss_top)
                cur_delta_bot = (alpha_bot * cur_delta_bot) + ((1 - alpha_bot) * dt_ss_bot)
            
            # Absolute Values
            t_top_sim = amb + cur_delta_top
            t_bot_sim = amb + cur_delta_bot
            
            # Hot spot approximation (not in doc but good to keep)
            # Delta_windings usually ~1.1 to 1.3 * top oil rise
            t_hot_sim = t_top_sim + (15 * (load_factor**1.6)) # Gradient assumed 15K at rated
            
            # Store results
            result_row = row.to_dict()
            # Remove helper col
            if 'dt_obj' in result_row: del result_row['dt_obj']
            
            result_row['hermetic_top_oil_C'] = round(t_top_sim, 2)
            result_row['hermetic_bottom_oil_C'] = round(t_bot_sim, 2)
            result_row['hot_spot_C'] = round(t_hot_sim, 2)
            
            # "Anlık Delta" values (Simulated Rise over Ambient)
            # These are exactly cur_delta_top and cur_delta_bot
            result_row['delta_top_C'] = round(cur_delta_top, 2)
            result_row['delta_bottom_C'] = round(cur_delta_bot, 2)
            
            enriched_rows.append(result_row)
            prev_time = cur_time
            
        return enriched_rows

if __name__ == "__main__":
    eng = HermeticSimulationEngine()
    print("Engine initialized with design values.")
