# Strategy comparison

Means over every scenario and simulated day (30 days x 3 scenarios each). Journey is drive plus wait. 'Others' wait' is the mean wait of the background drivers who do not use the app.

### Baseline: 200 app drivers a day

| Strategy | Journey (min) | 95% CI | Wait (min) | 95th pct wait | Waited at all | Drive (km) | Others' wait (min) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `queue_aware` | 3.1 | 2.9 to 3.2 | 0.2 | 0 | 2% | 0.99 | 31.9 |
| `static_queue` | 3.6 | 3.4 to 3.9 | 0.8 | 5 | 6% | 0.95 | 31.9 |
| `cost_optimized` | 5.8 | 5.4 to 6.4 | 2.6 | 16 | 11% | 1.08 | 31.9 |
| `range_aware` | 12.6 | 12.4 to 12.9 | 0.0 | 0 | 0% | 4.57 | 31.9 |
| `nearest` | 241.3 | 184.4 to 301.4 | 240.3 | 914 | 61% | 0.34 | 34.3 |
| `dijkstra` | 256.3 | 196.6 to 317.2 | 255.0 | 939 | 62% | 0.43 | 34.4 |

### High demand: 600 app drivers a day

| Strategy | Journey (min) | 95% CI | Wait (min) | 95th pct wait | Waited at all | Drive (km) | Others' wait (min) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `queue_aware` | 3.7 | 3.4 to 3.9 | 0.4 | 2 | 3% | 1.13 | 31.9 |
| `range_aware` | 12.7 | 12.4 to 12.9 | 0.0 | 0 | 0% | 4.57 | 31.9 |
| `static_queue` | 103.8 | 84.1 to 124.7 | 100.9 | 319 | 42% | 0.96 | 32.4 |
| `cost_optimized` | 150.5 | 128.0 to 175.0 | 147.3 | 421 | 54% | 1.08 | 32.9 |
| `nearest` | 792.1 | 598.8 to 987.0 | 791.1 | 2995 | 71% | 0.34 | 41.8 |
| `dijkstra` | 852.8 | 658.9 to 1071.6 | 851.5 | 3091 | 73% | 0.43 | 42.0 |
