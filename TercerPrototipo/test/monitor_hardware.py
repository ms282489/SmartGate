#!/usr/bin/env python3
"""Monitor independiente de recursos para Raspberry Pi / SmartGate.

Registra muestras continuas en CSV y genera resumen JSON al finalizar.
No modifica SmartGate ni requiere permisos de administrador normalmente.
"""
import argparse
import csv
import json
import os
import signal
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import psutil
except ImportError:
    sys.exit('Falta psutil. Instalar: python3 -m pip install psutil')

STOP = False

def stop_handler(signum, frame):
    global STOP
    STOP = True

def read_number(path, divisor=1.0):
    try:
        return float(Path(path).read_text().strip()) / divisor
    except (OSError, ValueError):
        return None

def vcgencmd(arg):
    try:
        p = subprocess.run(['vcgencmd', arg], capture_output=True, text=True, timeout=1.5, check=False)
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None

def arm_frequency_mhz():
    raw = read_number('/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq', 1000)
    if raw is not None:
        return raw
    raw = vcgencmd('measure_clock arm')
    try:
        return float(raw.split('=', 1)[1]) / 1e6 if raw else None
    except (ValueError, IndexError):
        return None

def temperature_c():
    temp = read_number('/sys/class/thermal/thermal_zone0/temp', 1000)
    if temp is not None:
        return temp
    raw = vcgencmd('measure_temp')
    try:
        return float(raw.split('=', 1)[1].split("'", 1)[0]) if raw else None
    except (ValueError, IndexError):
        return None

def throttled():
    raw = vcgencmd('get_throttled')
    if not raw or '=' not in raw:
        return None
    try:
        return int(raw.split('=', 1)[1], 16)
    except ValueError:
        return None

def safe(fn, default=None):
    try:
        return fn()
    except (psutil.Error, OSError, ValueError, ZeroDivisionError):
        return default

def get_processes(root_pid):
    if root_pid is None:
        return []
    try:
        root = psutil.Process(root_pid)
        return [root] + root.children(recursive=True)
    except psutil.Error:
        return []

def process_metrics(root_pid, cpu_last):
    procs = get_processes(root_pid)
    cpu_sum, rss, threads = 0.0, 0, 0
    current = set()
    for proc in procs:
        try:
            ident = (proc.pid, proc.create_time())
            current.add(ident)
            # La primera lectura de cada proceso sirve para inicializar su contador.
            if ident not in cpu_last:
                proc.cpu_percent(interval=None)
                cpu_last[ident] = True
            else:
                cpu_sum += proc.cpu_percent(interval=None)
            rss += proc.memory_info().rss
            threads += proc.num_threads()
        except psutil.Error:
            continue
    for ident in list(cpu_last):
        if ident not in current:
            del cpu_last[ident]
    return {
        'smartgate_process_count': len(current) if root_pid is not None else None,
        'smartgate_cpu_pct_one_core': round(cpu_sum, 2) if root_pid is not None else None,
        'smartgate_rss_mb_sum': round(rss / 1048576, 2) if root_pid is not None else None,
        'smartgate_threads': threads if root_pid is not None else None,
    }

def percentiles(values, percentile):
    if not values:
        return None
    values = sorted(values)
    k = (len(values)-1) * percentile / 100
    a, b = int(k), min(int(k)+1, len(values)-1)
    return values[a] + (values[b]-values[a])*(k-a)

def describe(values):
    if not values:
        return {'samples': 0, 'mean': None, 'p95': None, 'max': None, 'min': None}
    return {'samples': len(values), 'mean': round(statistics.mean(values), 2),
            'p95': round(percentiles(values, 95), 2), 'max': round(max(values), 2),
            'min': round(min(values), 2)}

def args_parse():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--interval', type=float, default=0.5, help='Segundos entre muestras (default 0.5)')
    p.add_argument('--duration', type=float, default=0, help='Duracion en segundos; 0 hasta Ctrl+C')
    p.add_argument('--pid', type=int, default=None, help='PID de SmartGate (incluye procesos hijos)')
    p.add_argument('--output', type=Path, default=None, help='Carpeta de resultados')
    args = p.parse_args()
    if args.interval < 0.2: p.error('--interval debe ser >= 0.2 s')
    if args.duration < 0: p.error('--duration no puede ser negativa')
    if args.pid is not None and not psutil.pid_exists(args.pid): p.error('PID no existe')
    if args.output is None:
        args.output = Path('resultados') / ('hardware_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    return args

def main():
    args = args_parse()
    args.output.mkdir(parents=True, exist_ok=True)
    csv_path = args.output / 'hardware.csv'
    summary_path = args.output / 'resumen_hardware.json'
    ncpu = psutil.cpu_count(logical=True) or 1
    fields = ['timestamp_iso', 'elapsed_s', 'cpu_total_pct'] + [f'cpu_core_{i}_pct' for i in range(ncpu)] + [
        'arm_freq_mhz', 'soc_temp_c', 'throttled_hex', 'under_voltage_now',
        'freq_capped_now', 'throttled_now', 'soft_temp_limit_now',
        'ram_used_mb', 'ram_available_mb', 'ram_used_pct', 'swap_used_mb',
        'smartgate_process_count', 'smartgate_cpu_pct_one_core',
        'smartgate_rss_mb_sum', 'smartgate_threads', 'disk_read_mb_total',
        'disk_write_mb_total']
    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    start = time.monotonic()
    next_sample = start
    samples = []
    cpu_last = {}
    psutil.cpu_percent(interval=None, percpu=True)
    process_metrics(args.pid, cpu_last)
    last_throttle = None
    print(f'Monitoreando cada {args.interval:g} s. PID={args.pid or "sin seleccionar"}')
    print(f'CSV: {csv_path.resolve()}')
    print('Detener con Ctrl+C; se guardara un resumen.')
    with csv_path.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        while not STOP:
            now = time.monotonic()
            if args.duration and now-start >= args.duration:
                break
            if now < next_sample:
                time.sleep(min(next_sample-now, 0.1))
                continue
            next_sample += args.interval
            if next_sample < now:
                next_sample = now + args.interval
            core = psutil.cpu_percent(interval=None, percpu=True)
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            disk = safe(psutil.disk_io_counters)
            th = throttled()
            if th is not None:
                last_throttle = th
            row = {
                'timestamp_iso': datetime.now(timezone.utc).astimezone().isoformat(timespec='milliseconds'),
                'elapsed_s': round(now-start, 3),
                'cpu_total_pct': round(sum(core)/len(core), 2) if core else None,
                'arm_freq_mhz': arm_frequency_mhz(),
                'soc_temp_c': temperature_c(),
                'throttled_hex': f'0x{th:x}' if th is not None else '',
                'under_voltage_now': bool(th & 0x1) if th is not None else None,
                'freq_capped_now': bool(th & 0x2) if th is not None else None,
                'throttled_now': bool(th & 0x4) if th is not None else None,
                'soft_temp_limit_now': bool(th & 0x8) if th is not None else None,
                'ram_used_mb': round(mem.used/1048576, 2),
                'ram_available_mb': round(mem.available/1048576, 2),
                'ram_used_pct': mem.percent,
                'swap_used_mb': round(swap.used/1048576, 2),
                'disk_read_mb_total': round(disk.read_bytes/1048576, 2) if disk else None,
                'disk_write_mb_total': round(disk.write_bytes/1048576, 2) if disk else None,
            }
            for i, value in enumerate(core): row[f'cpu_core_{i}_pct'] = value
            row.update(process_metrics(args.pid, cpu_last))
            writer.writerow(row)
            fh.flush()
            samples.append(row)
            if len(samples) % max(1, round(5 / args.interval)) == 0:
                print(f"{row['elapsed_s']:.0f}s | CPU {row['cpu_total_pct']}% | "
                      f"{row['soc_temp_c']} C | {row['arm_freq_mhz']} MHz | "
                      f"RAM {row['ram_used_mb']} MB")
    keys = ['cpu_total_pct', 'arm_freq_mhz', 'soc_temp_c', 'ram_used_mb',
            'ram_available_mb', 'swap_used_mb', 'smartgate_cpu_pct_one_core',
            'smartgate_rss_mb_sum', 'smartgate_threads'] + [f'cpu_core_{i}_pct' for i in range(ncpu)]
    summary = {
        'start_time': samples[0]['timestamp_iso'] if samples else None,
        'end_time': samples[-1]['timestamp_iso'] if samples else None,
        'duration_s': round(time.monotonic()-start, 2),
        'interval_requested_s': args.interval,
        'samples': len(samples),
        'smartgate_pid': args.pid,
        'cpu_process_scale': '100% equivale a un nucleo logico completo; puede superar 100%',
        'measurements': {key: describe([float(r[key]) for r in samples if r.get(key) is not None]) for key in keys},
        'throttled_last_hex': f'0x{last_throttle:x}' if last_throttle is not None else None,
        'under_voltage_now_samples': sum(r['under_voltage_now'] is True for r in samples),
        'throttled_now_samples': sum(r['throttled_now'] is True for r in samples),
        'historical_throttle_flags_last': {
            'under_voltage_occurred': bool(last_throttle & (1 << 16)),
            'frequency_capped_occurred': bool(last_throttle & (1 << 17)),
            'throttling_occurred': bool(last_throttle & (1 << 18)),
            'soft_temp_limit_occurred': bool(last_throttle & (1 << 19)),
        } if last_throttle is not None else None,
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nFinalizado: {len(samples)} muestras')
    print(f'CSV: {csv_path.resolve()}')
    print(f'Resumen: {summary_path.resolve()}')

if __name__ == '__main__':
    main()
