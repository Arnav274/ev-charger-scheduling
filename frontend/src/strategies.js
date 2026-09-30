// The six strategies, in the order the app and the experiment present them.
export const STRATEGIES = [
  {
    id: "nearest",
    label: "Nearest",
    description: "Shortest road distance, from OSRM. Ignores queues.",
  },
  {
    id: "dijkstra",
    label: "Dijkstra",
    description: "Fastest drive, from our own Dijkstra search over the London road graph. Ignores queues.",
  },
  {
    id: "cost_optimized",
    label: "Cost",
    description: "Weighs distance, predicted wait and price per kWh equally.",
  },
  {
    id: "static_queue",
    label: "Static queue",
    description: "Mostly predicted wait (Erlang-C), a little distance.",
  },
  {
    id: "queue_aware",
    label: "Queue aware",
    description: "As static queue, but chargers already booked for your arrival are counted as busy.",
  },
  {
    id: "range_aware",
    label: "Range aware",
    description: "Shortest predicted wait among stations you can reach on your current charge.",
  },
];

export const STRATEGY_LABELS = Object.fromEntries(STRATEGIES.map((s) => [s.id, s.label]));
