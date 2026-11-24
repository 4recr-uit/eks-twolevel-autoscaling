from pathlib import Path
import datetime as dt
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE = Path(__file__).resolve().parents[1] / 'results' / 'E3'
OUT = Path(__file__).resolve().parent / 'figures'
COLORS = {'keda': '#176b87', 'hpa': '#db7832'}
LABELS = {'keda': 'KEDA', 'hpa': 'HPA CPU'}
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False, 'axes.titleweight': 'bold', 'figure.facecolor': 'white', 'axes.grid': True, 'grid.alpha': .2})

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def when(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()

def samples(path, start, get):
    data = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    points = [(when(row['observed_at_utc']) - start, get(row['data'])) for row in data]
    return [(x, y) for x, y in points if -10 <= x <= 220]

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    reports = {v: read(BASE / f'E3-{v}-burst-r01' / 'report.json') for v in COLORS}
    metrics = [('Peak backlog', 'message', lambda r: r['peak_visible_plus_inflight_approx']),
               ('p95 completion time', 'seconds', lambda r: r['latency_seconds_approx_all_statuses']['p95']),
               ('Queue drain confirmation', 'seconds after load', lambda r: r['drain_confirmation_seconds_approx']),
               ('Ready workers', 'pod-minutes', lambda r: r['ready_pod_minutes_approx'])]
    fig, axes = plt.subplots(2, 2, figsize=(11.8, 7.2), layout='constrained')
    for ax, (title, unit, fn) in zip(axes.flat, metrics):
        values = [fn(reports[v]) for v in COLORS]
        bars = ax.bar(['KEDA', 'HPA CPU'], values, color=[COLORS[v] for v in COLORS], width=.55, zorder=3)
        ax.set_title(title, loc='left', pad=8); ax.set_ylabel(unit); ax.set_ylim(0, max(values)*1.24)
        ax.bar_label(bars, labels=[f'{v:,.2f}'.rstrip('0').rstrip('.') for v in values], padding=5, fontsize=11, fontweight='bold')
        ax.grid(axis='x', visible=False)
    fig.suptitle('E3 · Burst: KEDA vs CPU HPA', fontsize=17, fontweight='bold')
    fig.text(.5, -.02, 'SQS queue and latency values are estimates; pod-minutes cover load start to 60 seconds after load.', ha='center', fontsize=9, color='#555')
    fig.savefig(OUT / 'burst-comparison.png', dpi=180, bbox_inches='tight'); plt.close(fig)
    plot_timeline(reports)
    print('Generated', OUT)


def plot_timeline(reports):
    burst_start = 60
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True, layout='constrained')
    for v in COLORS:
        p = BASE / f'E3-{v}-burst-r01'; start = when(reports[v]['workload_started_utc'])
        worker = samples(p/'events/collect-worker-samples.jsonl', start, lambda x: (x['desired'], x['ready']))
        queue = samples(p/'metrics/collect-sqs-samples.jsonl', start, lambda x: sum(x['main']['counts'][k] for k in ('ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible')))
        nodes = samples(p/'events/collect-topology-samples.jsonl', start, lambda x: sum(n.get('labels', {}).get('karpenter.sh/nodepool') == 'e3-orders' for n in x['nodes']))
        for index, state, style, marker in ((1, 'Ready', '-', 'o'), (0, 'desired', '--', 's')):
            series = [(t, counts[index]) for t, counts in worker]
            before_burst = [count for t, count in series if t <= burst_start]
            label = f'{LABELS[v]} {state}'
            if before_burst:
                first_rise = next(((t, count) for t, count in series
                                   if t > burst_start and count > before_burst[-1]), None)
                if first_rise:
                    t, count = first_rise
                    axes[0].plot(t, count, marker=marker, color=COLORS[v], markeredgecolor='white',
                                 markersize=7, zorder=4)
            axes[0].step([t for t, _ in series], [count for _, count in series], where='post',
                         color=COLORS[v], linestyle=style, linewidth=2, label=label)
        axes[1].plot([x for x,y in queue], [y for x,y in queue], '.', color=COLORS[v], markersize=5, label=LABELS[v])
        axes[2].step([x for x,y in nodes], [y for x,y in nodes], where='post', color=COLORS[v], linewidth=2, label=LABELS[v])
    ticks = list(range(0, 211, 30))
    phases = {0: 'Load starts', burst_start: 'Burst starts', 90: 'Burst ends', 150: 'Load ends'}
    for ax in axes:
        ax.axvspan(burst_start, 90, color='#f3c78c', alpha=.3, zorder=0)
        for t in phases:
            ax.axvline(t, color='#776f65', linestyle=':', linewidth=1, zorder=1)
        ax.set_xticks(ticks, [f'{t} s\n{phases[t]}' if t in phases else f'{t} s' for t in ticks])
        ax.tick_params(axis='x', labelbottom=True, labelsize=9)
        ax.set_xlim(-10, 220)
        ax.set_ylim(bottom=0)
        ax.legend(loc='upper left', ncol=2, fontsize=9)
    axes[0].set_ylabel('Worker Pod'); axes[0].set_title('Desired and ready workers',loc='left')
    axes[1].set_ylabel('Message'); axes[1].set_title('SQS queue: visible + in-flight (estimated samples)',loc='left')
    axes[2].set_ylabel('Node'); axes[2].set_title('E3 worker nodes',loc='left'); axes[2].set_xlabel('Seconds since workload start')
    fig.suptitle('E3 · Burst over time',fontsize=17,fontweight='bold')
    fig.text(.5,-.015,'Shaded interval: 40 requests/s. All times are seconds since workload start.',ha='center',fontsize=9,color='#555')
    fig.savefig(OUT/'burst-timeline.png',dpi=180,bbox_inches='tight'); plt.close(fig)

if __name__ == '__main__':
    main()
