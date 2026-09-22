# Campaign failure rates

source: `range.db`
confidence 0.95, target upper bound 0.05

| design | environment | trials | failures | rate | exact interval | Wilson interval | exact upper | trials for target |
|---|---|---|---|---|---|---|---|---|
| Carter v2.4 | density 0.1, slope 15.0, friction 0.6/0.5, seed 7 | 1 | 0 | 0.0 | [0.0, 0.975] | [0.0, 0.7935] | 0.95 | 59 |
| Carter v2.4 | density 0.1, slope 25.0, friction 0.6/0.5, seed 7 | 1 | 0 | 0.0 | [0.0, 0.975] | [0.0, 0.7935] | 0.95 | 59 |
| Carter v2.4 | density 0.1, slope authored, friction 0.6/0.5, seed 7 | 1 | 1 | 1.0 | [0.025, 1.0] | [0.2065, 1.0] | 1.0 | 93 |
| Carter v2.4 | density 0.3, slope 15.0, friction 0.6/0.5, seed 7 | 1 | 0 | 0.0 | [0.0, 0.975] | [0.0, 0.7935] | 0.95 | 59 |
| Carter v2.4 | density 0.4, slope 15.0, friction 0.6/0.5, seed 7 | 1 | 0 | 0.0 | [0.0, 0.975] | [0.0, 0.7935] | 0.95 | 59 |
| Carter v2.4 | density 0.4, slope 25.0, friction 0.6/0.5, seed 7 | 1 | 0 | 0.0 | [0.0, 0.975] | [0.0, 0.7935] | 0.95 | 59 |
| Carter v2.4 | density 0.8, slope 15.0, friction 0.6/0.5, seed 7 | 1 | 1 | 1.0 | [0.025, 1.0] | [0.2065, 1.0] | 1.0 | 93 |
| Carter v2.4 | density 0.8, slope 25.0, friction 0.6/0.5, seed 7 | 1 | 0 | 0.0 | [0.0, 0.975] | [0.0, 0.7935] | 0.95 | 59 |
