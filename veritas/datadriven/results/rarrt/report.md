# Campaign failure rates

source: `campaign.db`
confidence 0.95, target upper bound 0.05

| design | environment | trials | failures | rate | exact interval | Wilson interval | exact upper | trials for target |
|---|---|---|---|---|---|---|---|---|
| cvar0.1 | all | 60 | 33 | 0.55 | [0.4161, 0.6788] | [0.4249, 0.6691] | 0.6602 | 877 |
| cvar0.5 | all | 60 | 32 | 0.5333 | [0.4, 0.6633] | [0.4089, 0.6537] | 0.6444 | 855 |
| cvar0.9 | all | 60 | 33 | 0.55 | [0.4161, 0.6788] | [0.4249, 0.6691] | 0.6602 | 877 |
| neutral | all | 60 | 34 | 0.5667 | [0.4324, 0.6941] | [0.441, 0.6843] | 0.6758 | 900 |
| rrtstar | all | 60 | 37 | 0.6167 | [0.4821, 0.7393] | [0.4902, 0.7291] | 0.7219 | 968 |

## Post-hoc robustness

| design | environment | n | mean | min | violated | 0.05 quantile | DKW-corrected |
|---|---|---|---|---|---|---|---|
| cvar0.1 | all | 60 | 0.4541 | 0.1475 | 0.0 | 0.1724 | -inf |
| cvar0.5 | all | 60 | 0.4401 | 0.1025 | 0.0 | 0.1624 | -inf |
| cvar0.9 | all | 60 | 0.3783 | 0.1325 | 0.0 | 0.157 | -inf |
| neutral | all | 60 | 0.4612 | 0.1575 | 0.0 | 0.1867 | -inf |
| rrtstar | all | 60 | 0.5438 | 0.235 | 0.0 | 0.235 | -inf |
