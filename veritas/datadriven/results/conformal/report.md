# Campaign failure rates

source: `campaign.db`
confidence 0.95, target upper bound 0.05

| design | environment | trials | failures | rate | exact interval | Wilson interval | exact upper | trials for target |
|---|---|---|---|---|---|---|---|---|
| degraded | all | 90 | 83 | 0.9222 | [0.8463, 0.9682] | [0.8481, 0.9618] | 0.9629 | 1985 |
| nominal | all | 90 | 68 | 0.7556 | [0.6536, 0.84] | [0.6575, 0.8327] | 0.8283 | 1657 |
| sharp | all | 90 | 51 | 0.5667 | [0.458, 0.6708] | [0.4636, 0.6642] | 0.6554 | 1282 |

## Post-hoc robustness

| design | environment | n | mean | min | violated | 0.05 quantile | DKW-corrected |
|---|---|---|---|---|---|---|---|
| degraded | all | 90 | -1.1116 | -1.7732 | 1.0 | -1.553 | -inf |
| nominal | all | 90 | -0.7542 | -1.3594 | 1.0 | -1.1827 | -inf |
| sharp | all | 90 | -0.5533 | -1.0782 | 1.0 | -0.9994 | -inf |
