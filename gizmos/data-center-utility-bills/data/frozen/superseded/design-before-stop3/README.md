# Superseded: step E on the design before Stop 3

These three files are step E's results on the design as it stood before the owner's Stop 3 rulings of 2026-11-18. They are kept here, unchanged, so the earlier run stays visible. **They are not results for the final design.**

- `inference_comparison_stage1.json`: stage 1 of the inference comparison (seed 20261201, 2,000 made-up datasets for each of 13 processes), committed at `e8fd020`.
- `inference_validation_stage2.json`: stage 2, the validation of the selected candidate (seed 20261202, 20,000 a process), committed at `f0f5fbd`.
- `power_simulation.json`: the power and range-width simulation under that selected procedure (seed 20261113, 2,000 draws), committed at `cc02b62`.

All three were run on the headline set at 2% of 7 hosts with Umatilla (19325:OR) and without Arizona Public Service: 59 units, 19 state clusters, 770 rows, 28 regressors. The comparison fingerprint is `3bbcd57166f4a99eb6f9a7504db5a2c2288cd032bf7ce6a81e1a02f49d2364ec`.

The Stop 3 rulings changed the design: Arizona Public Service came in, Umatilla went out, and the ownership table changed. The fingerprint rule (D-59 item 5) therefore requires the comparison, the validation and the simulation to be run again on the final design, with the same rules, seeds, counts and standard. Nothing here was extended. The runs on the final design are in `data/frozen/` under the same file names, and both runs are reported (D-98).

The made-up datasets for these runs are outside git, in `data/interim/inference_comparison_fingerprint_3bbcd571/`.
