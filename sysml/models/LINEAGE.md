# Model lineage

`AGR_stack-MB-SensorTrade-mk6.mdzip` is a byte-for-byte copy of
`MB-SensorTrade-Iddmbse_perfect-mk6.mdzip` from the lab's drop, renamed to say what it
holds. Nothing inside it was edited.

## The seven snapshots

All seven are one lineage of the same project (model root `AGR_stack`, saved by Magic
SoSA / MagicDraw UML 2022x). The element count is the number of XML start tags in the
archive member `com.nomagic.magicdraw.uml_model.model`, measured here with
`unzip -p <file> com.nomagic.magicdraw.uml_model.model | grep -o '<[A-Za-z]' | wc -l`.
Diagrams are counted from the same member as `<ownedDiagram ...>` elements.

| file (in the drop) | bytes | modified | elements | diagrams |
|---|---|---|---|---|
| `Iddmbse_v2.mdzip` | 4689120 | 2023-11-30 14:04 | 4658 | 33 |
| `Iddmbse_v2_perfect-mk1.mdzip` | 4248175 | 2023-12-02 17:37 | 4820 | 35 |
| `Iddmbse_v2_perfect-mk2.mdzip` | 4074092 | 2023-12-04 11:21 | 5761 | 41 |
| `Iddmbse_v2_perfect-mk3.mdzip` | 4111883 | 2023-12-04 17:10 | 6867 | 49 |
| `Iddmbse_v2_perfect-mk4.mdzip` | 4142241 | 2023-12-05 15:14 | 8246 | 51 |
| `Iddmbse_v2_perfect-mk5-SensorTrade.mdzip` | 4140338 | 2023-12-05 20:10 | 8832 | 50 |
| `MB-SensorTrade-Iddmbse_perfect-mk6.mdzip` | 4140535 | 2024-02-14 02:39 | 8875 | 51 |

The element count grows monotonically and packages are only ever added, so mk6 contains
everything the earlier snapshots contain. Byte size is not monotonic because the archive
is recompressed on every save. mk5 has one diagram fewer than mk4 and mk6 has it back.

Measured on mk6 and quoted in `../README.md`: 69 `sysml:Block`, 3 `sysml:ConstraintBlock`,
23 `sysml:Requirement`, 51 diagrams, 5 opaque expressions whose language is `Matlab` or
`matlab`.

## Where the originals are

Everything the user dropped is kept, unmodified, outside the repository, as `iddmbse_v2/`
(59 files, the folder as delivered) and `iddmbse_v2.zip` (the same folder zipped, 56 MB).
The repository holds only the curated copies.

## Left out of the repository on purpose

| left out | why |
|---|---|
| the six earlier snapshots (base, mk1 ... mk5) | superseded by mk6; roughly 4 MB each, no content of their own |
| six `.mdzip.bak` files (base, mk2, mk3, mk4, mk5, mk6) | MagicDraw autosave states written one to two seconds before their sibling; they differ by 0.6 to 18 KB (`Iddmbse_v2` -646 B, mk2 +607 B, mk3 +6371 B, mk4 +18506 B, mk5 +1683 B, mk6 +1992 B relative to the `.mdzip`) |
| `TurtleSim (2).mdzip` | an unrelated turtlesim / rosbridge tutorial project, not part of the AGR model |
