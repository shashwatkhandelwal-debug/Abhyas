#!/bin/sh
# usage: runall.sh view journey...   (sequential, one browser at a time)
view=$1; shift
for j in "$@"; do
  python -X utf8 -I scripts/bughunt/bh.py scripts/bughunt/journeys/$j.json --view $view --run ${j}_$view > "$TEMP/bughunt/${j}_$view.out" 2>&1
done
echo done > "$TEMP/bughunt/last_batch_$view.done"
