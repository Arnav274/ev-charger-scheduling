# Algorithm Comparison Table

| algorithm | mean_distance_km | ci_low_dist | ci_high_dist | mean_wait_min | ci_low_wait | ci_high_wait | mean_pdelay | acceptance_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| range_aware | 5.8258 | 5.3516 | 6.3175 | 0.0178 | 0.0 | 0.0444 | 0.0007 | 1.0 |
| static_queue | 3.7136 | 3.256 | 4.1445 | 0.0611 | 0.0506 | 0.072 | 0.004 | 0.99 |
| queue_aware | 3.8271 | 3.4185 | 4.2722 | 0.0641 | 0.0528 | 0.0764 | 0.0041 | 1.0 |
| cost_optimized | 3.6067 | 3.1938 | 4.0697 | 0.4948 | 0.3881 | 0.6058 | 0.0202 | 0.96 |
| nearest | 3.3805 | 2.9115 | 3.8253 | 15.4589 | 13.4266 | 17.6996 | 0.2169 | 0.69 |
| dijkstra | 3.5632 | 3.1303 | 4.0301 | 21.3456 | 19.0677 | 23.6022 | 0.2813 | 0.66 |
